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


# ---------- TTS (Emergent key expected) ----------
def test_tts_ok(s):
    r = s.post(f"{API}/tts", json={"text": "Hello from council.", "member_id": "gpt"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "audio_base64" in data
    assert isinstance(data["audio_base64"], str) and len(data["audio_base64"]) > 100


# ---------- New session-scoped: review / synthesize / export ----------
@pytest.fixture(scope="module")
def new_session(s):
    sess = s.post(f"{API}/sessions", json={
        "title": "TEST_new_features_session",
        "participant_ids": ["gpt", "claude", "gemini", "deepseek", "kimi"],
    }).json()
    sid = sess["id"]
    yield sid
    s.delete(f"{API}/sessions/{sid}")


def test_review_requires_two_speakers(s, new_session):
    # No turns yet -> should 400 "At least two members must speak..."
    r = s.post(f"{API}/sessions/{new_session}/review")
    assert r.status_code == 400
    detail = r.json().get("detail", "")
    assert "two members" in detail.lower()


def test_synthesize_without_openrouter_key(s, new_session):
    r = s.post(f"{API}/sessions/{new_session}/synthesize", json={"chairman_id": "gpt"})
    # No OpenRouter key -> graceful 400
    assert r.status_code in (400, 502), r.text


def test_synthesize_bad_chairman(s, new_session):
    r = s.post(f"{API}/sessions/{new_session}/synthesize", json={"chairman_id": "nobody"})
    assert r.status_code == 400


def test_export_pdf(s, new_session):
    # Add a couple of human turns
    s.post(f"{API}/sessions/{new_session}/message", json={"text": "First message."})
    s.post(f"{API}/sessions/{new_session}/message", json={"text": "Second message."})
    r = s.get(f"{API}/sessions/{new_session}/export")
    assert r.status_code == 200
    ct = r.headers.get("content-type", "")
    assert "application/pdf" in ct, f"unexpected content-type: {ct}"
    assert r.content[:4] == b"%PDF", "response is not a valid PDF"
    assert len(r.content) > 500


def test_export_not_found(s):
    r = s.get(f"{API}/sessions/nope-xyz/export")
    assert r.status_code == 404


# ---------- Security fixes ----------

# Input length caps
def test_message_length_cap(s):
    sess = s.post(f"{API}/sessions", json={"title": "TEST_len", "participant_ids": ["gpt"]}).json()
    sid = sess["id"]
    try:
        r = s.post(f"{API}/sessions/{sid}/message", json={"text": "a" * 8001})
        assert r.status_code == 422, f"expected 422 got {r.status_code}: {r.text}"
        # normal length still accepted
        ok = s.post(f"{API}/sessions/{sid}/message", json={"text": "a" * 100})
        assert ok.status_code == 200
    finally:
        s.delete(f"{API}/sessions/{sid}")


def test_synthesize_question_length_cap(s, new_session):
    r = s.post(f"{API}/sessions/{new_session}/synthesize",
               json={"chairman_id": "gpt", "question": "q" * 4001})
    assert r.status_code == 422, f"expected 422 got {r.status_code}: {r.text}"


def test_tts_length_cap(s):
    r = s.post(f"{API}/tts", json={"text": "t" * 8001})
    assert r.status_code == 422, f"expected 422 got {r.status_code}: {r.text}"


# STT hardening
def test_stt_rejects_non_audio(s):
    files = {"audio": ("hello.txt", b"just some text", "text/plain")}
    r = s.post(f"{API}/stt", files=files)
    assert r.status_code == 415, f"expected 415 got {r.status_code}: {r.text}"


def test_stt_accepts_small_mp3(s):
    # Minimal mp3-like bytes (ID3 header + silence). Emergent STT may reject audio content,
    # but our hardening should let it through (200 or 500 from upstream — NOT 415).
    mp3_bytes = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" + b"\x00" * 2048
    files = {"audio": ("rec.mp3", mp3_bytes, "audio/mpeg")}
    r = s.post(f"{API}/stt", files=files)
    # Must not be 415; content-type accepted. 200 or 500 depending on whisper.
    assert r.status_code != 415, f"got 415 for audio/mpeg: {r.text}"
    assert r.status_code in (200, 400, 500), f"unexpected {r.status_code}: {r.text}"


# CORS still works (allow_credentials=False)
def test_cors_council_ok(s):
    r = s.get(f"{API}/council", headers={"Origin": "https://example.com"})
    assert r.status_code == 200


# Rate limit burst should trigger 429 on an expensive endpoint.
# NOTE: Backend is behind an ingress that may load-balance across pods; using a single
# keep-alive requests.Session pins the TCP connection to one pod, so its in-memory
# bucket fills predictably. We use /sessions/{id}/review with an empty session so
# the endpoint short-circuits fast (400 "two members...") but still passes through
# the rate_limit() Depends. Any 429 with the exact detail proves the fix works.
def test_expensive_endpoint_rate_limit_burst():
    """Burst-fire /sessions/{id}/review (fast 400 short-circuit but still passes
    through rate_limit() Depends). Backend is behind a load-balancer so we fire
    many concurrent requests to saturate every pod's bucket."""
    import requests as rq
    from concurrent.futures import ThreadPoolExecutor
    sess = rq.post(f"{API}/sessions",
                   json={"title": "TEST_ratelimit", "participant_ids": ["gpt", "claude"]}).json()
    sid = sess["id"]
    url = f"{API}/sessions/{sid}/review"

    def hit(_):
        try:
            return rq.post(url, timeout=15).status_code
        except Exception:
            return "to"

    codes = []
    try:
        # up to 3 rounds of 200 concurrent requests until we see 429s
        for round_ in range(3):
            with ThreadPoolExecutor(max_workers=80) as ex:
                codes.extend(list(ex.map(hit, range(200))))
            if any(c == 429 for c in codes):
                break
    finally:
        rq.delete(f"{API}/sessions/{sid}")

    from collections import Counter
    dist = Counter(codes)
    n429 = dist.get(429, 0)
    assert n429 > 0, f"expected some 429s among concurrent expensive-endpoint burst; distribution={dist}"

    # Verify body detail on a follow-up call while bucket is still saturated
    r = rq.post(url, timeout=15)
    if r.status_code == 429:
        assert "rate limit" in r.json().get("detail", "").lower()
