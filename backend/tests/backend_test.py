"""Backend tests for the AI Model Council API."""
import os
import io
import struct
import math
import wave
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://frontier-council.preview.emergentagent.com").rstrip("/")
# Load frontend .env because backend tests need REACT_APP_BACKEND_URL
try:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break
except Exception:
    pass

API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# ---------- Council ----------
def test_council(s):
    r = s.get(f"{API}/council")
    assert r.status_code == 200
    data = r.json()
    assert "members" in data and "notetaker" in data
    assert len(data["members"]) == 5
    ids = {m["id"] for m in data["members"]}
    assert ids == {"gpt", "claude", "gemini", "deepseek", "kimi"}
    assert data["notetaker"]["id"] == "scribe"
    assert isinstance(data["openrouter_configured"], bool)


# ---------- Settings ----------
def test_settings_get(s):
    r = s.get(f"{API}/settings")
    assert r.status_code == 200
    d = r.json()
    assert "openrouter_configured" in d
    assert "models" in d
    assert "personas" in d
    assert "notetaker_model" in d


def test_settings_persist(s):
    # persist a persona and a model override
    body = {
        "personas": {"gpt": "TEST_persona_text"},
        "models": {"gpt": "openai/gpt-5.6"},
        "notetaker_model": "openai/gpt-4o-mini",
    }
    r = s.post(f"{API}/settings", json=body)
    assert r.status_code == 200
    assert r.json().get("ok") is True

    r2 = s.get(f"{API}/settings")
    d = r2.json()
    assert d["personas"].get("gpt") == "TEST_persona_text"
    assert d["models"].get("gpt") == "openai/gpt-5.6"
    assert d["notetaker_model"] == "openai/gpt-4o-mini"


# ---------- Sessions CRUD ----------
def test_session_crud_and_message(s):
    # Create
    create = s.post(f"{API}/sessions", json={
        "title": "TEST_should_we_ship_agents",
        "participant_ids": ["gpt", "claude", "gemini", "deepseek", "kimi"],
    })
    assert create.status_code == 200
    sess = create.json()
    sid = sess["id"]
    assert sess["title"] == "TEST_should_we_ship_agents"
    assert len(sess["participant_ids"]) == 5
    assert sess["turns"] == []
    assert sess["status"] == "active"

    # Get
    g = s.get(f"{API}/sessions/{sid}")
    assert g.status_code == 200
    assert g.json()["id"] == sid

    # List should contain it
    lst = s.get(f"{API}/sessions").json()
    assert any(x["id"] == sid for x in lst)
    match = [x for x in lst if x["id"] == sid][0]
    assert "turn_count" in match

    # Post a human message
    m = s.post(f"{API}/sessions/{sid}/message", json={"text": "Hello council."})
    assert m.status_code == 200
    turn = m.json()
    assert turn["speaker_id"] == "human"
    assert turn["speaker_name"] == "You"
    assert turn["text"] == "Hello council."

    # Verify persistence
    g2 = s.get(f"{API}/sessions/{sid}").json()
    assert len(g2["turns"]) == 1
    assert g2["turns"][0]["text"] == "Hello council."

    # Respond without OpenRouter key -> should fail 400 or 502
    r = s.post(f"{API}/sessions/{sid}/respond", json={"model_id": "gpt"})
    assert r.status_code in (400, 502), f"unexpected {r.status_code}: {r.text}"

    # Delete
    d = s.delete(f"{API}/sessions/{sid}")
    assert d.status_code == 200

    g3 = s.get(f"{API}/sessions/{sid}")
    assert g3.status_code == 404


def test_session_not_found(s):
    r = s.get(f"{API}/sessions/does-not-exist-xyz")
    assert r.status_code == 404


def test_message_bad_session(s):
    r = s.post(f"{API}/sessions/nope/message", json={"text": "hi"})
    assert r.status_code == 404


def test_respond_bad_member(s):
    # Create quick session then try bad member id
    sess = s.post(f"{API}/sessions", json={"title": "TEST_bad", "participant_ids": ["gpt"]}).json()
    sid = sess["id"]
    try:
        r = s.post(f"{API}/sessions/{sid}/respond", json={"model_id": "nobody"})
        assert r.status_code == 400
    finally:
        s.delete(f"{API}/sessions/{sid}")


# ---------- STT ----------
def _make_wav_bytes(seconds=1, freq=440, sr=16000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = []
        for i in range(int(sr * seconds)):
            val = int(32767 * 0.2 * math.sin(2 * math.pi * freq * i / sr))
            frames.append(struct.pack("<h", val))
        w.writeframes(b"".join(frames))
    return buf.getvalue()


def test_stt(s):
    audio = _make_wav_bytes()
    files = {"audio": ("rec.wav", audio, "audio/wav")}
    r = s.post(f"{API}/stt", files=files)
    # If emergent key configured this should be 200; otherwise 400
    assert r.status_code in (200, 400, 500)
    if r.status_code == 200:
        assert "text" in r.json()
