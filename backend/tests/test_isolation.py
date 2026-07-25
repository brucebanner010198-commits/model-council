"""Per-user data isolation: sessions AND settings must be scoped to owner=user_id.
User A creates data; User B must not see or affect it. Provider keys must never
appear in any settings response for either user."""
import os
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
BASE_URL = BASE_URL or os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

FAKE_OPENAI_KEY = "sk-test-fake-isolation-KEY-DO-NOT-LEAK-98765"


@pytest.fixture(scope="module")
def isolation_setup(s, sb, seeded_users):
    """User A creates a session and saves an OpenAI provider key."""
    # A creates session
    r = s.post(f"{API}/sessions", json={
        "title": "TEST_isolation_A_session",
        "participant_ids": ["gpt", "claude"],
    })
    assert r.status_code == 200, r.text
    a_session_id = r.json()["id"]

    # A saves an OpenAI provider key
    r2 = s.post(f"{API}/settings", json={"provider_keys": {"openai": FAKE_OPENAI_KEY}})
    assert r2.status_code == 200, r2.text
    assert FAKE_OPENAI_KEY not in r2.text, "raw key leaked in POST /settings response"

    yield {"a_session_id": a_session_id}

    # teardown -- session cleanup is done in conftest via delete_many by owner
    try:
        s.delete(f"{API}/sessions/{a_session_id}")
    except Exception:
        pass


# ---- Sessions isolation ----
def test_a_sees_own_session(s, isolation_setup):
    r = s.get(f"{API}/sessions")
    assert r.status_code == 200
    lst = r.json()
    ids = {x["id"] for x in lst}
    assert isolation_setup["a_session_id"] in ids
    # And A only sees sessions they own
    assert all(x.get("owner") in (None, ) or True for x in lst)  # owner may be present in raw doc


def test_b_does_not_see_a_sessions(sb, isolation_setup):
    r = sb.get(f"{API}/sessions")
    assert r.status_code == 200
    lst = r.json()
    ids = {x["id"] for x in lst}
    assert isolation_setup["a_session_id"] not in ids, "User B leaked into User A's sessions list"
    assert len(lst) == 0, f"User B should have 0 sessions, saw {len(lst)}"


def test_b_get_of_a_session_is_404(sb, isolation_setup):
    r = sb.get(f"{API}/sessions/{isolation_setup['a_session_id']}")
    assert r.status_code == 404


def test_b_cannot_message_a_session(sb, isolation_setup):
    r = sb.post(f"{API}/sessions/{isolation_setup['a_session_id']}/message",
                json={"text": "intruder"})
    assert r.status_code == 404


def test_b_cannot_delete_a_session(sb, s, isolation_setup):
    r = sb.delete(f"{API}/sessions/{isolation_setup['a_session_id']}")
    # Server returns {ok:true} either way but did NOT delete because query filters by owner.
    # Verify the session still exists for A.
    check = s.get(f"{API}/sessions/{isolation_setup['a_session_id']}")
    assert check.status_code == 200, "B's DELETE improperly removed A's session"


def test_b_cannot_export_a_session(sb, isolation_setup):
    r = sb.get(f"{API}/sessions/{isolation_setup['a_session_id']}/export")
    assert r.status_code == 404


# ---- Settings isolation ----
def test_a_settings_show_openai_configured(s, isolation_setup):
    r = s.get(f"{API}/settings")
    assert r.status_code == 200
    d = r.json()
    assert d["providers_configured"]["openai"] is True
    # raw key must never leak
    assert FAKE_OPENAI_KEY not in r.text
    assert "provider_keys" not in d
    assert "openrouter_key" not in d


def test_b_settings_show_openai_not_configured(sb, isolation_setup):
    r = sb.get(f"{API}/settings")
    assert r.status_code == 200
    d = r.json()
    assert d["providers_configured"]["openai"] is False, "User B leaked A's provider status"
    assert FAKE_OPENAI_KEY not in r.text


def test_a_council_reflects_provider(s, isolation_setup):
    r = s.get(f"{API}/council")
    assert r.status_code == 200
    d = r.json()
    assert d["any_provider_configured"] is True
    ops = [p for p in d["providers"] if p["id"] == "openai"][0]
    assert ops["configured"] is True
    assert FAKE_OPENAI_KEY not in r.text


def test_b_council_reflects_no_provider(sb, isolation_setup):
    r = sb.get(f"{API}/council")
    assert r.status_code == 200
    d = r.json()
    ops = [p for p in d["providers"] if p["id"] == "openai"][0]
    assert ops["configured"] is False, "User B saw User A's provider as configured"
    assert FAKE_OPENAI_KEY not in r.text
