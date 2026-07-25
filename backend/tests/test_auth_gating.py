"""Auth gating: every protected /api endpoint returns 401 without a valid session.
Only /api/ (root), /api/auth/session and /api/auth/logout are public."""
import os
import io
import struct
import math
import wave
import pytest
import requests

BASE_URL = None
try:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break
except Exception:
    pass
BASE_URL = BASE_URL or os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def anon():
    """Anonymous requests session (NO auth header, NO cookie)."""
    return requests.Session()


# ---- Public endpoints ----
def test_root_is_public(anon):
    r = anon.get(f"{API}/")
    assert r.status_code == 200
    assert r.json().get("message")


def test_auth_session_invalid_returns_401(anon):
    r = anon.post(f"{API}/auth/session", json={"session_id": "not-a-real-emergent-session"})
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"


def test_auth_logout_is_public(anon):
    # /auth/logout has no auth dependency; called with no cookie it's a no-op that succeeds.
    r = anon.post(f"{API}/auth/logout")
    assert r.status_code == 200
    assert r.json().get("ok") is True


# ---- Protected endpoints: all should return 401 without auth ----
PROTECTED_GET = [
    "/council",
    "/settings",
    "/sessions",
    "/sessions/any-id",
    "/sessions/any-id/export",
    "/openrouter/models",
    "/auth/me",
]

PROTECTED_POST = [
    ("/settings", {}),
    ("/sessions", {"title": "x", "participant_ids": ["gpt"]}),
    ("/sessions/any-id/message", {"text": "hi"}),
    ("/sessions/any-id/respond", {"model_id": "gpt"}),
    ("/sessions/any-id/notes", {}),
    ("/sessions/any-id/conclude", {"drafter_id": "gpt"}),
    ("/sessions/any-id/review", {}),
    ("/sessions/any-id/synthesize", {"chairman_id": "gpt"}),
    ("/tts", {"text": "hello"}),
]


@pytest.mark.parametrize("path", PROTECTED_GET)
def test_protected_get_returns_401(anon, path):
    r = anon.get(f"{API}{path}")
    assert r.status_code == 401, f"{path} expected 401, got {r.status_code}"


@pytest.mark.parametrize("path,body", PROTECTED_POST)
def test_protected_post_returns_401(anon, path, body):
    r = anon.post(f"{API}{path}", json=body)
    assert r.status_code == 401, f"{path} expected 401, got {r.status_code}"


def test_stt_protected(anon):
    # multipart POST without auth
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 100)
    files = {"audio": ("rec.wav", buf.getvalue(), "audio/wav")}
    r = anon.post(f"{API}/stt", files=files)
    assert r.status_code == 401, f"expected 401, got {r.status_code}"


def test_bogus_bearer_token_returns_401(anon):
    r = anon.get(f"{API}/auth/me",
                 headers={"Authorization": "Bearer this-token-does-not-exist"})
    assert r.status_code == 401


def test_bogus_cookie_returns_401(anon):
    r = anon.get(f"{API}/auth/me",
                 cookies={"session_token": "no-such-token-here"})
    assert r.status_code == 401


# ---- Sanity: with a valid Bearer token, auth/me & /council work ----
def test_valid_bearer_returns_user(seeded_users):
    tok = seeded_users["a"]["token"]
    r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    data = r.json()
    assert data["user_id"] == seeded_users["a"]["user_id"]
    assert data["email"] == seeded_users["a"]["email"]


def test_valid_bearer_council_ok(seeded_users):
    tok = seeded_users["a"]["token"]
    r = requests.get(f"{API}/council", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["members"]) == 5
    assert data["notetaker"]["id"] == "scribe"


def test_valid_cookie_auth_works(seeded_users):
    tok = seeded_users["a"]["token"]
    r = requests.get(f"{API}/auth/me", cookies={"session_token": tok})
    assert r.status_code == 200
    assert r.json()["user_id"] == seeded_users["a"]["user_id"]
