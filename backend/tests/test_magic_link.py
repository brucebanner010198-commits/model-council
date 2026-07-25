"""Magic link (passwordless email) auth tests.

Covers:
- POST /api/auth/magic/request with no RESEND_API_KEY → 503
- POST /api/auth/magic/request invalid email body → 422
- POST /api/auth/magic/verify bogus token → 400
- POST /api/auth/magic/verify happy path (seeded doc) → user + session cookie + single-use
- Merge-by-email: verify token for existing user reuses same user_id + shared sessions
- Expired token → 400 'expired'
"""
import hashlib
import secrets
import time
import uuid
import pytest
import requests
from datetime import datetime, timedelta, timezone

from conftest import API, MONGO_URL, DB_NAME  # noqa
from pymongo import MongoClient


@pytest.fixture(scope="module")
def mdb():
    mc = MongoClient(MONGO_URL)
    yield mc[DB_NAME]
    mc.close()


@pytest.fixture
def cleanup_tracker(mdb):
    """Track and clean up docs we insert during a test."""
    tracker = {"users": [], "user_sessions": [], "magic_links": [], "sessions": [], "settings": []}
    yield tracker
    try:
        if tracker["users"]:
            mdb.users.delete_many({"user_id": {"$in": tracker["users"]}})
        if tracker["user_sessions"]:
            mdb.user_sessions.delete_many({"user_id": {"$in": tracker["user_sessions"]}})
        if tracker["magic_links"]:
            mdb.magic_links.delete_many({"token_hash": {"$in": tracker["magic_links"]}})
        if tracker["sessions"]:
            mdb.sessions.delete_many({"id": {"$in": tracker["sessions"]}})
        if tracker["settings"]:
            mdb.settings.delete_many({"_id": {"$in": tracker["settings"]}})
    except Exception as e:
        print(f"[cleanup] {e}")


def _seed_magic(mdb, email, tracker, minutes=15, used=False):
    raw = secrets.token_urlsafe(32)
    h = hashlib.sha256(raw.encode()).hexdigest()
    expires = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    mdb.magic_links.insert_one({
        "email": email, "token_hash": h, "used": used,
        "expires_at": expires.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    tracker["magic_links"].append(h)
    return raw, h


# ---------------- REQUEST ----------------

def test_magic_request_returns_503_without_resend_key():
    r = requests.post(f"{API}/auth/magic/request",
                      json={"email": "person@example.com"})
    assert r.status_code == 503, f"got {r.status_code}: {r.text}"
    body = r.json()
    detail = body.get("detail", "").lower()
    assert "not configured" in detail or "resend" in detail


def test_magic_request_invalid_email_returns_422():
    r = requests.post(f"{API}/auth/magic/request",
                      json={"email": "not-a-real-email"})
    assert r.status_code == 422, f"got {r.status_code}: {r.text}"


def test_magic_request_missing_email_returns_422():
    r = requests.post(f"{API}/auth/magic/request", json={})
    assert r.status_code == 422


# ---------------- VERIFY ----------------

def test_magic_verify_bogus_token_returns_400():
    r = requests.post(f"{API}/auth/magic/verify",
                      json={"token": "definitely-not-a-real-token-xyz"})
    assert r.status_code == 400, f"got {r.status_code}: {r.text}"
    detail = r.json().get("detail", "").lower()
    assert "invalid" in detail or "already used" in detail


def test_magic_verify_happy_path_creates_user_and_session(mdb, cleanup_tracker):
    email = f"test.magic.new.{int(time.time()*1000)}@example.com"
    raw, h = _seed_magic(mdb, email, cleanup_tracker)

    r = requests.post(f"{API}/auth/magic/verify", json={"token": raw})
    assert r.status_code == 200, f"got {r.status_code}: {r.text}"
    body = r.json()
    assert body["email"] == email
    assert body["user_id"].startswith("user_")
    cleanup_tracker["users"].append(body["user_id"])
    cleanup_tracker["user_sessions"].append(body["user_id"])

    # session cookie must be set
    cookies = r.cookies
    assert "session_token" in cookies
    session_token = cookies["session_token"]

    # user_sessions row exists
    sess = mdb.user_sessions.find_one({"session_token": session_token})
    assert sess is not None
    assert sess["user_id"] == body["user_id"]

    # magic_links doc now used
    doc = mdb.magic_links.find_one({"token_hash": h})
    assert doc["used"] is True

    # Verify auth works with the returned cookie
    me = requests.get(f"{API}/auth/me",
                      headers={"Authorization": f"Bearer {session_token}"})
    assert me.status_code == 200
    assert me.json()["email"] == email

    # Single-use: second verify with same token → 400
    r2 = requests.post(f"{API}/auth/magic/verify", json={"token": raw})
    assert r2.status_code == 400
    d = r2.json().get("detail", "").lower()
    assert "invalid" in d or "already used" in d


def test_magic_verify_expired_token_returns_400(mdb, cleanup_tracker):
    email = f"test.magic.expired.{int(time.time()*1000)}@example.com"
    # Seed with expiry in the past
    raw = secrets.token_urlsafe(32)
    h = hashlib.sha256(raw.encode()).hexdigest()
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    mdb.magic_links.insert_one({
        "email": email, "token_hash": h, "used": False,
        "expires_at": past.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    cleanup_tracker["magic_links"].append(h)

    r = requests.post(f"{API}/auth/magic/verify", json={"token": raw})
    assert r.status_code == 400, f"got {r.status_code}: {r.text}"
    detail = r.json().get("detail", "").lower()
    assert "expired" in detail


# ---------------- MERGE BY EMAIL (critical) ----------------

def test_magic_verify_merges_with_existing_user_by_email(mdb, cleanup_tracker):
    """A prior Google login for jane@x.com created user_id 'existing_uid_...'.
    A magic-link login for the SAME email must resolve to that same user_id
    and see the SAME sessions."""
    ts = int(time.time() * 1000)
    email = f"test.merge.jane.{ts}@example.com"
    existing_uid = f"existing_uid_{ts}"
    cleanup_tracker["users"].append(existing_uid)
    cleanup_tracker["user_sessions"].append(existing_uid)
    cleanup_tracker["settings"].append(existing_uid)

    # Simulate prior Google login: user + a session owned by them + a settings doc
    mdb.users.insert_one({
        "user_id": existing_uid, "email": email,
        "name": "Jane Prior", "picture": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    prior_session_id = str(uuid.uuid4())
    cleanup_tracker["sessions"].append(prior_session_id)
    mdb.sessions.insert_one({
        "id": prior_session_id, "owner": existing_uid,
        "title": "Jane's prior council", "participant_ids": ["gpt", "claude"],
        "turns": [], "notes": [], "conclusion": None, "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    mdb.settings.insert_one({
        "_id": existing_uid, "openrouter_key": "sk-or-prior-fake",
    })

    # Also give her a prior google session_token (should still exist after magic login)
    prior_token = f"prior_google_token_{ts}"
    mdb.user_sessions.insert_one({
        "user_id": existing_uid, "session_token": prior_token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    # Now do the magic-link login for the SAME email
    raw, _ = _seed_magic(mdb, email, cleanup_tracker)
    r = requests.post(f"{API}/auth/magic/verify", json={"token": raw})
    assert r.status_code == 200, f"got {r.status_code}: {r.text}"
    body = r.json()

    # CRITICAL: same user_id — no duplicate user created
    assert body["user_id"] == existing_uid, \
        f"Expected same user_id {existing_uid}, got {body['user_id']} (merge failed!)"
    assert body["email"] == email

    # No duplicate user by email
    dupes = list(mdb.users.find({"email": email}))
    assert len(dupes) == 1, f"Duplicate users for {email}: {[d['user_id'] for d in dupes]}"

    # New session_token from magic login sees Jane's prior sessions
    new_token = r.cookies["session_token"]
    listed = requests.get(f"{API}/sessions",
                         headers={"Authorization": f"Bearer {new_token}"})
    assert listed.status_code == 200
    ids = [s["id"] for s in listed.json()]
    assert prior_session_id in ids, \
        f"Prior session {prior_session_id} not visible after merge! Got {ids}"


# ---------------- Sanity: verify doesn't leak _id ----------------

def test_magic_verify_response_no_mongo_id(mdb, cleanup_tracker):
    email = f"test.magic.noid.{int(time.time()*1000)}@example.com"
    raw, _ = _seed_magic(mdb, email, cleanup_tracker)
    r = requests.post(f"{API}/auth/magic/verify", json={"token": raw})
    assert r.status_code == 200
    body = r.json()
    cleanup_tracker["users"].append(body["user_id"])
    cleanup_tracker["user_sessions"].append(body["user_id"])
    assert "_id" not in body
