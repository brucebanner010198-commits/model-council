"""Shared fixtures: seed two test users A and B directly in Mongo,
provide authenticated requests sessions with Bearer tokens,
and clean up all test-created data at the end."""
import os
import time
import pytest
import requests
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient


def _load_env(path):
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return env


_BE = _load_env("/app/backend/.env")
_FE = _load_env("/app/frontend/.env")

MONGO_URL = _BE.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = _BE.get("DB_NAME", "test_database")
BASE_URL = (_FE.get("REACT_APP_BACKEND_URL")
            or os.environ.get("REACT_APP_BACKEND_URL", "")).rstrip("/")
API = f"{BASE_URL}/api"


def _seed_user(mdb, tag):
    ts = int(time.time() * 1000)
    uid = f"test-user-{tag}-{ts}"
    token = f"test_session_{tag}_{ts}"
    email = f"test.user.{tag}.{ts}@example.com"
    mdb.users.insert_one({
        "user_id": uid, "email": email,
        "name": f"Test User {tag.upper()}", "picture": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    mdb.user_sessions.insert_one({
        "user_id": uid, "session_token": token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return uid, token, email


@pytest.fixture(scope="session")
def mongo():
    mc = MongoClient(MONGO_URL)
    yield mc[DB_NAME]
    mc.close()


@pytest.fixture(scope="session")
def seeded_users(mongo):
    a_uid, a_tok, a_email = _seed_user(mongo, "a")
    b_uid, b_tok, b_email = _seed_user(mongo, "b")
    data = {
        "a": {"user_id": a_uid, "token": a_tok, "email": a_email},
        "b": {"user_id": b_uid, "token": b_tok, "email": b_email},
    }
    yield data
    # ---- Cleanup ----
    try:
        # Delete any sessions owned by test users
        mongo.sessions.delete_many({"owner": {"$in": [a_uid, b_uid]}})
        mongo.settings.delete_many({"_id": {"$in": [a_uid, b_uid]}})
        mongo.user_sessions.delete_many({"user_id": {"$in": [a_uid, b_uid]}})
        mongo.users.delete_many({"user_id": {"$in": [a_uid, b_uid]}})
    except Exception as e:
        print(f"[cleanup] warning: {e}")


@pytest.fixture(scope="module")
def s(seeded_users):
    """Authed requests.Session as user A (default for regression tests)."""
    sess = requests.Session()
    sess.headers.update({
        "Authorization": f"Bearer {seeded_users['a']['token']}",
    })
    return sess


@pytest.fixture(scope="module")
def sb(seeded_users):
    """Authed requests.Session as user B."""
    sess = requests.Session()
    sess.headers.update({
        "Authorization": f"Bearer {seeded_users['b']['token']}",
    })
    return sess


@pytest.fixture(scope="module")
def api_base():
    return API


@pytest.fixture(scope="module")
def token_a(seeded_users):
    return seeded_users["a"]["token"]


@pytest.fixture(scope="module")
def token_b(seeded_users):
    return seeded_users["b"]["token"]
