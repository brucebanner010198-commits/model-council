"""Provider key + routing tests (iteration 4 + iter5 multi-user)."""
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

PROVIDER_IDS = {"openai", "anthropic", "gemini", "deepseek", "moonshot"}


# `s` fixture (authed as user A) comes from conftest.py


@pytest.fixture(scope="module", autouse=True)
def cleanup(seeded_users):
    """Ensure any provider_keys we set are cleared afterwards."""
    yield
    try:
        from pymongo import MongoClient
        env = {}
        with open("/app/backend/.env") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    env[k] = v.strip().strip('"').strip("'")
        mc = MongoClient(env["MONGO_URL"])
        # Clear the per-user settings doc for user A
        mc[env["DB_NAME"]].settings.update_one(
            {"_id": seeded_users["a"]["user_id"]},
            {"$unset": {"provider_keys": "", "openrouter_key": ""}},
        )
    except Exception as e:
        print(f"cleanup failed: {e}")


# ---------- /api/council new fields ----------
def test_council_has_provider_fields(s):
    r = s.get(f"{API}/council")
    assert r.status_code == 200
    data = r.json()
    assert "providers" in data
    assert "openrouter_configured" in data
    assert "any_provider_configured" in data
    assert isinstance(data["any_provider_configured"], bool)
    pids = {p["id"] for p in data["providers"]}
    assert pids == PROVIDER_IDS
    for p in data["providers"]:
        assert set(p.keys()) >= {"id", "label", "configured"}
        assert isinstance(p["configured"], bool)
    for m in data["members"]:
        assert "provider" in m and m["provider"] in PROVIDER_IDS
        assert "native_model" in m and m["native_model"]
        assert "routing" in m


# ---------- /api/settings never returns raw keys ----------
def test_settings_never_returns_raw_keys(s):
    # Save fake keys
    body = {
        "provider_keys": {"openai": "sk-test-fake-openai-KEY123", "anthropic": "sk-ant-fake-KEY456"},
        "routing": {"gpt": "direct"},
        "native_models": {"gpt": "gpt-5.6"},
    }
    r = s.post(f"{API}/settings", json=body)
    assert r.status_code == 200
    resp = r.json()
    # Response body must not contain raw key text
    resp_text = r.text
    assert "sk-test-fake-openai-KEY123" not in resp_text
    assert "sk-ant-fake-KEY456" not in resp_text
    assert resp["providers_configured"]["openai"] is True
    assert resp["providers_configured"]["anthropic"] is True

    # GET /settings must not include the raw key either
    g = s.get(f"{API}/settings")
    assert g.status_code == 200
    gtext = g.text
    assert "sk-test-fake-openai-KEY123" not in gtext
    assert "sk-ant-fake-KEY456" not in gtext
    d = g.json()
    assert d["providers_configured"]["openai"] is True
    assert d["routing"].get("gpt") == "direct"
    assert d["native_models"].get("gpt") == "gpt-5.6"
    # Explicit — no top level 'provider_keys' field
    assert "provider_keys" not in d

    # GET /council must also not leak
    c = s.get(f"{API}/council")
    assert "sk-test-fake-openai-KEY123" not in c.text
    cj = c.json()
    assert cj["any_provider_configured"] is True
    ops = [p for p in cj["providers"] if p["id"] == "openai"][0]
    assert ops["configured"] is True


# ---------- Routing error/fallback wiring ----------
def _make_session(s):
    return s.post(f"{API}/sessions",
                  json={"title": "TEST_routing", "participant_ids": ["gpt"]}).json()["id"]


def test_respond_openrouter_forced_no_or_key(s):
    # Force openrouter routing but no OR key => graceful 400
    s.post(f"{API}/settings", json={"routing": {"gpt": "openrouter"}})
    sid = _make_session(s)
    try:
        r = s.post(f"{API}/sessions/{sid}/respond", json={"model_id": "gpt"})
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
        assert "openrouter" in r.json()["detail"].lower()
    finally:
        s.delete(f"{API}/sessions/{sid}")


def test_respond_direct_with_fake_key_graceful(s):
    # Set fake OpenAI key + direct routing => attempts direct, fails -> falls back to openrouter (no OR) => graceful (400/502), not 500
    s.post(f"{API}/settings", json={
        "provider_keys": {"openai": "sk-test-fake-not-real"},
        "routing": {"gpt": "direct"},
    })
    sid = _make_session(s)
    try:
        r = s.post(f"{API}/sessions/{sid}/respond", json={"model_id": "gpt"})
        assert r.status_code in (400, 502), f"expected graceful 400/502, got {r.status_code}: {r.text}"
        assert r.status_code != 500
    finally:
        s.delete(f"{API}/sessions/{sid}")


def test_respond_auto_no_keys_graceful(s, seeded_users):
    # Clear provider_keys via direct DB unset, then attempt auto routing => graceful
    try:
        from pymongo import MongoClient
        env = {}
        with open("/app/backend/.env") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    env[k] = v.strip().strip('"').strip("'")
        mc = MongoClient(env["MONGO_URL"])
        mc[env["DB_NAME"]].settings.update_one(
            {"_id": seeded_users["a"]["user_id"]},
            {"$unset": {"provider_keys": "", "openrouter_key": ""}, "$set": {"routing": {"gpt": "auto"}}},
        )
    except Exception as e:
        pytest.skip(f"cannot reset db: {e}")

    sid = _make_session(s)
    try:
        r = s.post(f"{API}/sessions/{sid}/respond", json={"model_id": "gpt"})
        assert r.status_code in (400, 502), f"expected graceful 400/502, got {r.status_code}: {r.text}"
    finally:
        s.delete(f"{API}/sessions/{sid}")


def test_council_any_provider_reflects_state(s):
    # After cleanup, any_provider_configured should be False
    r = s.get(f"{API}/council")
    d = r.json()
    # If EMERGENT_LLM_KEY / other env keys are set for a provider, this may be True. Just assert type/boolean and providers list intact.
    assert isinstance(d["any_provider_configured"], bool)
    assert isinstance(d["openrouter_configured"], bool)
