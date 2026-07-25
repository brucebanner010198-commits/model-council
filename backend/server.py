from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import tempfile
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime, timezone
import httpx

from emergentintegrations.llm.openai import OpenAITextToSpeech, OpenAISpeechToText

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')
OPENROUTER_URL = "https://openrouter.ai/api/v1"

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------- Council roster (defaults, model ids editable via settings) ----------------
COUNCIL = [
    {"id": "gpt", "name": "GPT-5.6", "org": "OpenAI", "country": "US", "open": False,
     "specialty": "Reasoning & Mathematics", "color": "#10B981", "voice": "onyx",
     "model": "openai/gpt-5.6"},
    {"id": "claude", "name": "Claude Opus 5", "org": "Anthropic", "country": "US", "open": False,
     "specialty": "Coding & Language", "color": "#F59E0B", "voice": "sage",
     "model": "anthropic/claude-opus-4.6"},
    {"id": "gemini", "name": "Gemini 3.1 Pro", "org": "Google", "country": "US", "open": False,
     "specialty": "Instruction Following", "color": "#8B5CF6", "voice": "nova",
     "model": "google/gemini-3-pro-preview"},
    {"id": "deepseek", "name": "DeepSeek V4 Pro", "org": "DeepSeek", "country": "China", "open": True,
     "specialty": "Math & Open Reasoning", "color": "#EF4444", "voice": "echo",
     "model": "deepseek/deepseek-chat"},
    {"id": "kimi", "name": "Kimi K3", "org": "Moonshot AI", "country": "China", "open": True,
     "specialty": "Open-Weight Reasoning", "color": "#3B82F6", "voice": "fable",
     "model": "moonshotai/kimi-k2"},
]
NOTETAKER = {"id": "scribe", "name": "Scribe", "org": "Council Secretariat",
             "color": "#a1a1aa", "model": "openai/gpt-4o-mini"}
MEMBERS_BY_ID = {m["id"]: m for m in COUNCIL}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------------- Models ----------------
class SettingsUpdate(BaseModel):
    openrouter_key: Optional[str] = None
    models: Optional[dict] = None          # {member_id: model_id}
    notetaker_model: Optional[str] = None
    personas: Optional[dict] = None        # {member_id: persona_text}


class SessionCreate(BaseModel):
    title: str
    participant_ids: List[str]


class HumanMessage(BaseModel):
    text: str


class RespondRequest(BaseModel):
    model_id: str
    directive: Optional[str] = None


class ConcludeRequest(BaseModel):
    drafter_id: str


# ---------------- Settings helpers ----------------
async def get_settings():
    doc = await db.settings.find_one({"_id": "global"}, {"_id": 0})
    return doc or {}


async def get_openrouter_key():
    s = await get_settings()
    return s.get("openrouter_key") or os.environ.get("OPENROUTER_API_KEY") or ""


async def resolved_member(mid: str):
    base = dict(MEMBERS_BY_ID[mid])
    s = await get_settings()
    overrides = s.get("models", {})
    personas = s.get("personas", {})
    if mid in overrides and overrides[mid]:
        base["model"] = overrides[mid]
    base["persona"] = personas.get(mid, "")
    return base


async def call_openrouter(model: str, messages: list, max_tokens: int = 500):
    key = await get_openrouter_key()
    if not key:
        raise HTTPException(status_code=400, detail="OpenRouter API key not configured. Add it in Settings.")
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://frontier-council.preview.emergentagent.com",
        "X-Title": "AI Model Council",
    }
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens}
    async with httpx.AsyncClient(timeout=120) as hc:
        r = await hc.post(f"{OPENROUTER_URL}/chat/completions", headers=headers, json=payload)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"OpenRouter error ({model}): {r.text[:300]}")
    data = r.json()
    return data["choices"][0]["message"]["content"].strip()


def transcript_text(turns, participants):
    names = ", ".join([m["name"] for m in participants])
    lines = []
    for t in turns:
        lines.append(f"{t['speaker_name']}: {t['text']}")
    return "\n".join(lines) if lines else "(No one has spoken yet.)"


def build_persona_prompt(member, participants, custom_persona):
    others = ", ".join([f"{m['name']} ({m['org']})" for m in participants if m["id"] != member["id"]])
    base = (
        f"You are {member['name']} from {member['org']}, a member of a live AI Model Council. "
        f"Your recognised strength is {member['specialty']}. "
        f"You are seated in a spoken roundtable with a Human and other frontier models: {others}. "
        "Speak naturally and conversationally, exactly like a sharp human expert in a real meeting. "
        "Be concise: 2 to 5 sentences. Have real opinions, build on or respectfully challenge others by name, "
        "and push the discussion toward insight. This is a free-speech forum, so be direct and critical when warranted. "
        "You are speaking OUT LOUD, so never use markdown, bullet points, headings, code fences or emoji. Just talk."
    )
    if custom_persona:
        base += f" Additional persona direction from the human: {custom_persona}"
    return base


# ---------------- Routes ----------------
@api_router.get("/")
async def root():
    return {"message": "AI Model Council API"}


@api_router.get("/council")
async def council():
    members = [await resolved_member(m["id"]) for m in COUNCIL]
    s = await get_settings()
    nt = dict(NOTETAKER)
    nt["model"] = s.get("notetaker_model") or NOTETAKER["model"]
    return {
        "members": members,
        "notetaker": nt,
        "openrouter_configured": bool(await get_openrouter_key()),
    }


@api_router.get("/settings")
async def read_settings():
    s = await get_settings()
    return {
        "openrouter_configured": bool(await get_openrouter_key()),
        "models": s.get("models", {}),
        "personas": s.get("personas", {}),
        "notetaker_model": s.get("notetaker_model") or NOTETAKER["model"],
    }


@api_router.post("/settings")
async def update_settings(body: SettingsUpdate):
    update = {}
    if body.openrouter_key is not None:
        update["openrouter_key"] = body.openrouter_key.strip()
    if body.models is not None:
        update["models"] = body.models
    if body.notetaker_model is not None:
        update["notetaker_model"] = body.notetaker_model
    if body.personas is not None:
        update["personas"] = body.personas
    await db.settings.update_one({"_id": "global"}, {"$set": update}, upsert=True)
    return {"ok": True, "openrouter_configured": bool(await get_openrouter_key())}


@api_router.get("/openrouter/models")
async def list_openrouter_models():
    key = await get_openrouter_key()
    if not key:
        raise HTTPException(status_code=400, detail="OpenRouter API key not configured.")
    async with httpx.AsyncClient(timeout=30) as hc:
        r = await hc.get(f"{OPENROUTER_URL}/models", headers={"Authorization": f"Bearer {key}"})
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="Could not fetch models from OpenRouter.")
    ids = sorted([m["id"] for m in r.json().get("data", [])])
    return {"models": ids}


@api_router.post("/sessions")
async def create_session(body: SessionCreate):
    sess = {
        "id": str(uuid.uuid4()),
        "title": body.title,
        "participant_ids": [p for p in body.participant_ids if p in MEMBERS_BY_ID],
        "turns": [],
        "notes": [],
        "conclusion": None,
        "status": "active",
        "created_at": now_iso(),
    }
    await db.sessions.insert_one(dict(sess))
    return sess


@api_router.get("/sessions")
async def list_sessions():
    docs = await db.sessions.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    for d in docs:
        d["turn_count"] = len(d.get("turns", []))
    return docs


@api_router.get("/sessions/{sid}")
async def get_session(sid: str):
    doc = await db.sessions.find_one({"id": sid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")
    return doc


@api_router.delete("/sessions/{sid}")
async def delete_session(sid: str):
    await db.sessions.delete_one({"id": sid})
    return {"ok": True}


@api_router.post("/sessions/{sid}/message")
async def add_message(sid: str, body: HumanMessage):
    turn = {
        "id": str(uuid.uuid4()),
        "speaker_id": "human",
        "speaker_name": "You",
        "color": "#ffffff",
        "text": body.text.strip(),
        "ts": now_iso(),
    }
    res = await db.sessions.update_one({"id": sid}, {"$push": {"turns": turn}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return turn


@api_router.post("/sessions/{sid}/respond")
async def respond(sid: str, body: RespondRequest):
    doc = await db.sessions.find_one({"id": sid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")
    if body.model_id not in MEMBERS_BY_ID:
        raise HTTPException(status_code=400, detail="Unknown council member")

    member = await resolved_member(body.model_id)
    participants = [await resolved_member(p) for p in doc["participant_ids"]]
    system = build_persona_prompt(member, participants, member.get("persona"))
    convo = transcript_text(doc["turns"], participants)
    directive = body.directive or f"Give your next contribution to the discussion as {member['name']}."
    user_prompt = f"Here is the council discussion so far:\n\n{convo}\n\n{directive}"

    text = await call_openrouter(member["model"], [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt},
    ], max_tokens=400)

    # Voice
    audio_b64 = None
    if EMERGENT_LLM_KEY:
        try:
            tts = OpenAITextToSpeech(api_key=EMERGENT_LLM_KEY)
            audio_b64 = await tts.generate_speech_base64(
                text=text[:4000], model="tts-1", voice=member["voice"])
        except Exception as e:
            logger.warning(f"TTS failed: {e}")

    turn = {
        "id": str(uuid.uuid4()),
        "speaker_id": member["id"],
        "speaker_name": member["name"],
        "color": member["color"],
        "text": text,
        "ts": now_iso(),
    }
    await db.sessions.update_one({"id": sid}, {"$push": {"turns": turn}})
    return {"turn": turn, "audio_base64": audio_b64}


@api_router.post("/sessions/{sid}/notes")
async def update_notes(sid: str):
    doc = await db.sessions.find_one({"id": sid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")
    participants = [await resolved_member(p) for p in doc["participant_ids"]]
    convo = transcript_text(doc["turns"], participants)
    if not doc["turns"]:
        return {"notes": []}
    s = await get_settings()
    nt_model = s.get("notetaker_model") or NOTETAKER["model"]
    system = (
        "You are Scribe, the council's dedicated note-taker. Read the discussion and extract the key points: "
        "important claims, decisions, agreements, disagreements and open questions. "
        "Return a concise list of short takeaways, ONE per line, no numbering, no markdown symbols, no preamble."
    )
    text = await call_openrouter(nt_model, [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Discussion:\n\n{convo}"},
    ], max_tokens=500)
    points = [ln.strip("-•* \t") for ln in text.split("\n") if ln.strip()]
    notes = [{"id": str(uuid.uuid4()), "text": p, "ts": now_iso()} for p in points]
    await db.sessions.update_one({"id": sid}, {"$set": {"notes": notes}})
    return {"notes": notes}


@api_router.post("/sessions/{sid}/conclude")
async def conclude(sid: str, body: ConcludeRequest):
    doc = await db.sessions.find_one({"id": sid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")
    if body.drafter_id not in MEMBERS_BY_ID:
        raise HTTPException(status_code=400, detail="Unknown drafter")
    member = await resolved_member(body.drafter_id)
    participants = [await resolved_member(p) for p in doc["participant_ids"]]
    convo = transcript_text(doc["turns"], participants)
    system = (
        f"You are {member['name']} from {member['org']}. The council has assigned you to draft the FINAL CONCLUSION "
        "of this discussion. Synthesise everything into a clear, well-structured written conclusion: the core "
        "decision or recommendation, the reasoning, and any important caveats or next steps. This is a written "
        "document (not spoken), so use clear paragraphs. Be decisive and insightful."
    )
    text = await call_openrouter(member["model"], [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Council discussion:\n\n{convo}\n\nDraft the final conclusion now."},
    ], max_tokens=900)
    conclusion = {"text": text, "drafter_id": member["id"], "drafter_name": member["name"], "ts": now_iso()}
    await db.sessions.update_one({"id": sid}, {"$set": {"conclusion": conclusion, "status": "concluded"}})
    return conclusion


@api_router.post("/stt")
async def speech_to_text(audio: UploadFile = File(...)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=400, detail="Voice key not configured")
    data = await audio.read()
    suffix = os.path.splitext(audio.filename or "rec.webm")[1] or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        stt = OpenAISpeechToText(api_key=EMERGENT_LLM_KEY)
        with open(tmp_path, "rb") as fh:
            result = await stt.transcribe(file=fh, model="whisper-1")
        text = getattr(result, "text", None) or (result.get("text") if isinstance(result, dict) else str(result))
        return {"text": text}
    except Exception as e:
        logger.error(f"STT failed: {e}")
        raise HTTPException(status_code=500, detail="Transcription failed")
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
