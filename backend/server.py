from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Request, Depends, Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import asyncio
import contextvars
import secrets
import hashlib
import tempfile
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
import uuid
import json
import random
from io import BytesIO
from datetime import datetime, timezone, timedelta
import httpx
import resend
from fastapi.responses import StreamingResponse

from emergentintegrations.llm.openai import OpenAITextToSpeech, OpenAISpeechToText

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'onboarding@resend.dev')
resend.api_key = RESEND_API_KEY
OPENROUTER_URL = "https://openrouter.ai/api/v1"

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------- Native provider endpoints (OpenAI-compatible) ----------------
PROVIDERS = {
    "openai": {"label": "OpenAI", "base": "https://api.openai.com/v1"},
    "anthropic": {"label": "Anthropic", "base": "https://api.anthropic.com/v1"},
    "gemini": {"label": "Google Gemini", "base": "https://generativelanguage.googleapis.com/v1beta/openai"},
    "deepseek": {"label": "DeepSeek", "base": "https://api.deepseek.com/v1"},
    "moonshot": {"label": "Moonshot (Kimi)", "base": "https://api.moonshot.ai/v1"},
}

# ---------------- Council roster (defaults; model ids & routing editable via settings) ----------------
COUNCIL = [
    {"id": "gpt", "name": "GPT-5.6", "org": "OpenAI", "country": "US", "open": False,
     "specialty": "Reasoning & Mathematics", "color": "#10B981", "voice": "onyx",
     "provider": "openai", "native_model": "gpt-5.6", "model": "openai/gpt-5.6"},
    {"id": "claude", "name": "Claude Opus 5", "org": "Anthropic", "country": "US", "open": False,
     "specialty": "Coding & Language", "color": "#F59E0B", "voice": "sage",
     "provider": "anthropic", "native_model": "claude-opus-4-6", "model": "anthropic/claude-opus-4.6"},
    {"id": "gemini", "name": "Gemini 3.1 Pro", "org": "Google", "country": "US", "open": False,
     "specialty": "Instruction Following", "color": "#8B5CF6", "voice": "nova",
     "provider": "gemini", "native_model": "gemini-3-pro-preview", "model": "google/gemini-3-pro-preview"},
    {"id": "deepseek", "name": "DeepSeek V4 Pro", "org": "DeepSeek", "country": "China", "open": True,
     "specialty": "Math & Open Reasoning", "color": "#EF4444", "voice": "echo",
     "provider": "deepseek", "native_model": "deepseek-chat", "model": "deepseek/deepseek-chat"},
    {"id": "kimi", "name": "Kimi K3", "org": "Moonshot AI", "country": "China", "open": True,
     "specialty": "Open-Weight Reasoning", "color": "#3B82F6", "voice": "fable",
     "provider": "moonshot", "native_model": "kimi-k2", "model": "moonshotai/kimi-k2"},
]
NOTETAKER = {"id": "scribe", "name": "Scribe", "org": "Council Secretariat", "color": "#a1a1aa",
             "provider": "openai", "native_model": "gpt-4o-mini", "model": "openai/gpt-4o-mini",
             "voice": "alloy", "specialty": "Note-taking", "routing": "auto", "persona": ""}
MEMBERS_BY_ID = {m["id"]: m for m in COUNCIL}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------------- Auth (Emergent Google, multi-user) ----------------
EMERGENT_AUTH_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"
_current_user_id = contextvars.ContextVar("current_user_id", default=None)


class User(BaseModel):
    user_id: str
    email: str
    name: str = ""
    picture: str = ""


class SessionExchange(BaseModel):
    session_id: str


class MagicRequest(BaseModel):
    email: EmailStr


class MagicVerify(BaseModel):
    token: str = Field(..., max_length=256)


async def get_current_user(request: Request) -> User:
    token = request.cookies.get("session_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    sess = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not sess:
        raise HTTPException(status_code=401, detail="Invalid session")
    exp = sess["expires_at"]
    if isinstance(exp, str):
        exp = datetime.fromisoformat(exp)
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")
    user = await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    _current_user_id.set(user["user_id"])
    return User(user_id=user["user_id"], email=user.get("email", ""),
                name=user.get("name", ""), picture=user.get("picture", ""))


# ---------------- Basic in-memory rate limiting (cost-abuse protection) ----------------
from collections import defaultdict, deque
import time

RATE_LIMIT = int(os.environ.get("RATE_LIMIT", "60"))      # requests per window
RATE_WINDOW = 60                                          # seconds
_rate_buckets = defaultdict(deque)
MAX_AUDIO_BYTES = 25 * 1024 * 1024                        # 25 MB (Whisper ceiling)
ALLOWED_AUDIO = {
    "audio/webm", "audio/ogg", "audio/mpeg", "audio/mp3", "audio/wav",
    "audio/x-wav", "audio/mp4", "audio/m4a", "audio/x-m4a", "application/octet-stream",
}


def rate_limit(request: Request):
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    dq = _rate_buckets[ip]
    while dq and dq[0] < now - RATE_WINDOW:
        dq.popleft()
    if len(dq) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please slow down and try again shortly.")
    dq.append(now)


# ---------------- Models ----------------
class SettingsUpdate(BaseModel):
    openrouter_key: Optional[str] = None
    provider_keys: Optional[dict] = None   # {provider_id: api_key}
    models: Optional[dict] = None          # {member_id: openrouter_model_id}
    native_models: Optional[dict] = None   # {member_id: native_model_name}
    routing: Optional[dict] = None         # {member_id: "auto"|"direct"|"openrouter"}
    notetaker_model: Optional[str] = None
    personas: Optional[dict] = None        # {member_id: persona_text}


class SessionCreate(BaseModel):
    title: str
    participant_ids: List[str]


class HumanMessage(BaseModel):
    text: str = Field(..., max_length=8000)


class RespondRequest(BaseModel):
    model_id: str
    directive: Optional[str] = Field(None, max_length=2000)


class ConcludeRequest(BaseModel):
    drafter_id: str


# ---------------- Settings helpers ----------------
async def get_settings():
    uid = _current_user_id.get()
    if not uid:
        return {}
    doc = await db.settings.find_one({"_id": uid}, {"_id": 0})
    return doc or {}


async def get_openrouter_key():
    s = await get_settings()
    return s.get("openrouter_key") or os.environ.get("OPENROUTER_API_KEY") or ""


async def get_provider_key(provider_id: str):
    s = await get_settings()
    pk = s.get("provider_keys", {}) or {}
    return pk.get(provider_id) or os.environ.get(f"{provider_id.upper()}_API_KEY") or ""


async def resolved_member(mid: str):
    base = dict(MEMBERS_BY_ID[mid])
    s = await get_settings()
    overrides = s.get("models", {}) or {}
    native = s.get("native_models", {}) or {}
    routing = s.get("routing", {}) or {}
    personas = s.get("personas", {}) or {}
    if overrides.get(mid):
        base["model"] = overrides[mid]
    if native.get(mid):
        base["native_model"] = native[mid]
    base["routing"] = routing.get(mid, "auto")
    base["persona"] = personas.get(mid, "")
    return base


class ProviderError(Exception):
    pass


async def call_openai_compatible(base: str, key: str, model: str, messages: list, max_tokens: int):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens}
    async with httpx.AsyncClient(timeout=120) as hc:
        r = await hc.post(f"{base}/chat/completions", headers=headers, json=payload)
    if r.status_code != 200:
        raise ProviderError(f"HTTP {r.status_code}: {r.text[:200]}")
    return r.json()["choices"][0]["message"]["content"].strip()


async def generate(member: dict, system: str, user: str, max_tokens: int = 500):
    """Route a member's completion: prefer native subscription/provider, fall back to OpenRouter per-model."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    pref = member.get("routing", "auto")
    provider = member.get("provider")
    prov_key = await get_provider_key(provider) if provider else ""

    if pref == "openrouter":
        routes = ["openrouter"]
    elif pref == "direct":
        routes = ["direct", "openrouter"]
    else:  # auto
        routes = ["direct", "openrouter"] if prov_key else ["openrouter"]

    last_err = None
    for route in routes:
        try:
            if route == "direct":
                if not prov_key:
                    raise ProviderError(f"No API key for {provider}")
                base = PROVIDERS[provider]["base"]
                text = await call_openai_compatible(base, prov_key, member["native_model"], messages, max_tokens)
                logger.info(f"{member.get('name')} answered via {provider} (direct)")
                return text
            else:
                text = await call_openrouter(member["model"], messages, max_tokens)
                logger.info(f"{member.get('name')} answered via OpenRouter fallback")
                return text
        except HTTPException as e:
            last_err = e
            continue
        except Exception as e:
            last_err = e
            logger.warning(f"Route {route} failed for {member.get('name')}: {e}")
            continue

    if isinstance(last_err, HTTPException):
        raise last_err
    raise HTTPException(status_code=502,
                        detail=f"No provider available for {member.get('name')}. Add a subscription key or an OpenRouter key in Settings.")


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
        logger.warning(f"OpenRouter error {r.status_code} for {model}: {r.text[:500]}")
        raise HTTPException(status_code=502, detail=f"OpenRouter error for {model} (HTTP {r.status_code}). Check the model ID in Settings.")
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


async def _login_user(email: str, name: str, picture: str, response: Response):
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        upd = {}
        if name:
            upd["name"] = name
        if picture:
            upd["picture"] = picture
        if upd:
            await db.users.update_one({"user_id": user_id}, {"$set": upd})
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({"user_id": user_id, "email": email,
                                   "name": name or email.split("@")[0], "picture": picture or "",
                                   "created_at": now_iso()})
    session_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await db.user_sessions.insert_one({"user_id": user_id, "session_token": session_token,
                                       "expires_at": expires_at.isoformat(), "created_at": now_iso()})
    response.set_cookie("session_token", session_token, httponly=True, secure=True,
                        samesite="none", path="/", max_age=7 * 24 * 3600)
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return {"user_id": user_id, "email": email, "name": u.get("name", ""), "picture": u.get("picture", "")}


@api_router.post("/auth/session")
async def auth_session(body: SessionExchange, response: Response):
    async with httpx.AsyncClient(timeout=30) as hc:
        r = await hc.get(EMERGENT_AUTH_URL, headers={"X-Session-ID": body.session_id})
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired session_id")
    data = r.json()
    email = data.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="No email in session data")
    return await _login_user(email, data.get("name", ""), data.get("picture", ""), response)


@api_router.post("/auth/magic/request")
async def magic_request(body: MagicRequest, request: Request, _rl: None = Depends(rate_limit)):
    email = body.email.strip().lower()
    if not RESEND_API_KEY:
        raise HTTPException(status_code=503, detail="Email sign-in is not configured yet. Add a RESEND_API_KEY.")
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    await db.magic_links.insert_one({
        "email": email, "token_hash": token_hash, "used": False,
        "expires_at": expires_at.isoformat(), "created_at": now_iso(),
    })
    origin = request.headers.get("origin") or os.environ.get("APP_BASE_URL", "")
    link = f"{origin}/login#magic={token}"
    html = f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#050505;padding:40px 0;font-family:Arial,Helvetica,sans-serif;">
      <tr><td align="center">
        <table width="440" cellpadding="0" cellspacing="0" style="background:#0a0a0c;border:1px solid #1f1f22;border-radius:16px;padding:36px;">
          <tr><td style="color:#a1a1aa;font-size:12px;letter-spacing:3px;text-transform:uppercase;">The Council</td></tr>
          <tr><td style="color:#ffffff;font-size:24px;font-weight:600;padding-top:14px;">Your sign-in link</td></tr>
          <tr><td style="color:#a1a1aa;font-size:14px;line-height:22px;padding-top:12px;">Click below to enter the council chamber. This link works once and expires in 15 minutes.</td></tr>
          <tr><td style="padding-top:26px;">
            <a href="{link}" style="display:inline-block;background:#ffffff;color:#050505;text-decoration:none;font-size:15px;font-weight:600;padding:13px 26px;border-radius:999px;">Sign in to The Council</a>
          </td></tr>
          <tr><td style="color:#52525b;font-size:12px;padding-top:24px;">If you didn't request this, you can safely ignore this email.</td></tr>
        </table>
      </td></tr>
    </table>"""
    params = {"from": SENDER_EMAIL, "to": [email], "subject": "Your sign-in link to The Council", "html": html}
    try:
        await asyncio.to_thread(resend.Emails.send, params)
    except Exception as e:
        logger.error(f"Magic link email failed: {e}")
        raise HTTPException(status_code=502, detail="Could not send the sign-in email. Please try again.")
    return {"ok": True}


@api_router.post("/auth/magic/verify")
async def magic_verify(body: MagicVerify, response: Response):
    token_hash = hashlib.sha256(body.token.strip().encode()).hexdigest()
    doc = await db.magic_links.find_one({"token_hash": token_hash})
    if not doc or doc.get("used"):
        raise HTTPException(status_code=400, detail="This sign-in link is invalid or already used.")
    exp = doc["expires_at"]
    if isinstance(exp, str):
        exp = datetime.fromisoformat(exp)
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="This sign-in link has expired. Please request a new one.")
    await db.magic_links.update_one({"_id": doc["_id"]}, {"$set": {"used": True}})
    return await _login_user(doc["email"], "", "", response)


@api_router.get("/auth/me")
async def auth_me(user: User = Depends(get_current_user)):
    return user


@api_router.post("/auth/logout")
async def auth_logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


async def _provider_status():
    status = {}
    for pid in PROVIDERS:
        status[pid] = bool(await get_provider_key(pid))
    return status


@api_router.get("/council")
async def council(user: User = Depends(get_current_user)):
    members = [await resolved_member(m["id"]) for m in COUNCIL]
    s = await get_settings()
    nt = dict(NOTETAKER)
    nt["native_model"] = s.get("notetaker_model") or NOTETAKER["native_model"]
    provider_status = await _provider_status()
    return {
        "members": members,
        "notetaker": nt,
        "providers": [{"id": pid, "label": PROVIDERS[pid]["label"], "configured": provider_status[pid]}
                      for pid in PROVIDERS],
        "openrouter_configured": bool(await get_openrouter_key()),
        "any_provider_configured": any(provider_status.values()),
    }


@api_router.get("/settings")
async def read_settings(user: User = Depends(get_current_user)):
    s = await get_settings()
    return {
        "openrouter_configured": bool(await get_openrouter_key()),
        "providers_configured": await _provider_status(),
        "models": s.get("models", {}),
        "native_models": s.get("native_models", {}),
        "routing": s.get("routing", {}),
        "personas": s.get("personas", {}),
        "notetaker_model": s.get("notetaker_model") or NOTETAKER["native_model"],
    }


@api_router.post("/settings")
async def update_settings(body: SettingsUpdate, user: User = Depends(get_current_user)):
    update = {}
    if body.openrouter_key is not None:
        update["openrouter_key"] = body.openrouter_key.strip()
    if body.provider_keys is not None:
        s = await get_settings()
        pk = dict(s.get("provider_keys", {}) or {})
        for k, v in body.provider_keys.items():
            if k in PROVIDERS and v and v.strip():
                pk[k] = v.strip()
        update["provider_keys"] = pk
    if body.models is not None:
        update["models"] = body.models
    if body.native_models is not None:
        update["native_models"] = body.native_models
    if body.routing is not None:
        update["routing"] = body.routing
    if body.notetaker_model is not None:
        update["notetaker_model"] = body.notetaker_model
    if body.personas is not None:
        update["personas"] = body.personas
    await db.settings.update_one({"_id": user.user_id}, {"$set": update}, upsert=True)
    return {"ok": True, "openrouter_configured": bool(await get_openrouter_key()),
            "providers_configured": await _provider_status()}


@api_router.get("/openrouter/models")
async def list_openrouter_models(user: User = Depends(get_current_user)):
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
async def create_session(body: SessionCreate, user: User = Depends(get_current_user)):
    sess = {
        "id": str(uuid.uuid4()),
        "owner": user.user_id,
        "title": body.title,
        "participant_ids": [p for p in body.participant_ids if p in MEMBERS_BY_ID],
        "turns": [],
        "notes": [],
        "conclusion": None,
        "status": "active",
        "created_at": now_iso(),
    }
    await db.sessions.insert_one(dict(sess))
    sess.pop("_id", None)
    return sess


@api_router.get("/sessions")
async def list_sessions(user: User = Depends(get_current_user)):
    docs = await db.sessions.find({"owner": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    for d in docs:
        d["turn_count"] = len(d.get("turns", []))
    return docs


@api_router.get("/sessions/{sid}")
async def get_session(sid: str, user: User = Depends(get_current_user)):
    doc = await db.sessions.find_one({"id": sid, "owner": user.user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")
    return doc


@api_router.delete("/sessions/{sid}")
async def delete_session(sid: str, user: User = Depends(get_current_user)):
    await db.sessions.delete_one({"id": sid, "owner": user.user_id})
    return {"ok": True}


@api_router.post("/sessions/{sid}/message")
async def add_message(sid: str, body: HumanMessage, user: User = Depends(get_current_user)):
    turn = {
        "id": str(uuid.uuid4()),
        "speaker_id": "human",
        "speaker_name": "You",
        "color": "#ffffff",
        "text": body.text.strip(),
        "ts": now_iso(),
    }
    res = await db.sessions.update_one({"id": sid, "owner": user.user_id}, {"$push": {"turns": turn}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return turn


@api_router.post("/sessions/{sid}/respond")
async def respond(sid: str, body: RespondRequest, user: User = Depends(get_current_user), _rl: None = Depends(rate_limit)):
    doc = await db.sessions.find_one({"id": sid, "owner": user.user_id}, {"_id": 0})
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

    text = await generate(member, system, user_prompt, max_tokens=400)

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
    await db.sessions.update_one({"id": sid, "owner": user.user_id}, {"$push": {"turns": turn}})
    return {"turn": turn, "audio_base64": audio_b64}


@api_router.post("/sessions/{sid}/notes")
async def update_notes(sid: str, user: User = Depends(get_current_user), _rl: None = Depends(rate_limit)):
    doc = await db.sessions.find_one({"id": sid, "owner": user.user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")
    participants = [await resolved_member(p) for p in doc["participant_ids"]]
    convo = transcript_text(doc["turns"], participants)
    if not doc["turns"]:
        return {"notes": []}
    s = await get_settings()
    nt = dict(NOTETAKER)
    nt["native_model"] = s.get("notetaker_model") or NOTETAKER["native_model"]
    nt["model"] = s.get("notetaker_model") if (s.get("notetaker_model") or "").startswith(("openai/", "google/", "anthropic/", "deepseek/", "moonshotai/")) else NOTETAKER["model"]
    nt["routing"] = "auto"
    system = (
        "You are Scribe, the council's dedicated note-taker. Read the discussion and extract the key points: "
        "important claims, decisions, agreements, disagreements and open questions. "
        "Return a concise list of short takeaways, ONE per line, no numbering, no markdown symbols, no preamble."
    )
    text = await generate(nt, system, f"Discussion:\n\n{convo}", max_tokens=500)
    points = [ln.strip("-•* \t") for ln in text.split("\n") if ln.strip()]
    notes = [{"id": str(uuid.uuid4()), "text": p, "ts": now_iso()} for p in points]
    await db.sessions.update_one({"id": sid, "owner": user.user_id}, {"$set": {"notes": notes}})
    return {"notes": notes}


@api_router.post("/sessions/{sid}/conclude")
async def conclude(sid: str, body: ConcludeRequest, user: User = Depends(get_current_user), _rl: None = Depends(rate_limit)):
    doc = await db.sessions.find_one({"id": sid, "owner": user.user_id}, {"_id": 0})
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
    text = await generate(member, system, f"Council discussion:\n\n{convo}\n\nDraft the final conclusion now.", max_tokens=900)
    conclusion = {"text": text, "drafter_id": member["id"], "drafter_name": member["name"], "ts": now_iso()}
    await db.sessions.update_one({"id": sid, "owner": user.user_id}, {"$set": {"conclusion": conclusion, "status": "concluded"}})
    return conclusion


@api_router.post("/stt")
async def speech_to_text(audio: UploadFile = File(...), user: User = Depends(get_current_user), _rl: None = Depends(rate_limit)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=400, detail="Voice key not configured")
    if not audio.content_type or audio.content_type.split(";")[0] not in ALLOWED_AUDIO:
        raise HTTPException(status_code=415, detail="Unsupported or missing audio type")
    data = b""
    while True:
        chunk = await audio.read(1024 * 1024)
        if not chunk:
            break
        data += chunk
        if len(data) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="Audio too large (max 25 MB)")
    suffix = os.path.splitext(os.path.basename(audio.filename or "rec.webm"))[1].lower()
    if suffix not in {".webm", ".ogg", ".mp3", ".mpeg", ".mpga", ".wav", ".mp4", ".m4a", ".flac"}:
        suffix = ".webm"
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


def _parse_json(raw: str):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end != -1:
        raw = raw[start:end + 1]
    return json.loads(raw)


async def _compute_review(participants, turns):
    """Blind peer review over each member's latest statement in `turns`."""
    positions = []
    for p in participants:
        last = None
        for t in turns:
            if t["speaker_id"] == p["id"]:
                last = t["text"]
        if last:
            positions.append({"member": p, "text": last})
    if len(positions) < 2:
        raise HTTPException(status_code=400, detail="At least two members must speak before a peer review.")

    order = list(range(len(positions)))
    random.shuffle(order)
    letters = [chr(65 + i) for i in range(len(positions))]
    letter_to_pos = {}
    anon_lines = []
    for i, li in enumerate(order):
        letter_to_pos[letters[i]] = positions[li]
        anon_lines.append(f"{letters[i]}: {positions[li]['text']}")
    anon_block = "\n\n".join(anon_lines)
    letter_list = ", ".join(letter_to_pos.keys())
    n = len(letter_to_pos)
    borda = {l: 0 for l in letter_to_pos}
    votes = {l: 0 for l in letter_to_pos}

    async def review_one(reviewer):
        system = (
            f"You are {reviewer['name']}, acting as an impartial council reviewer. The following positions are "
            "anonymised — you do not know who authored any of them, so judge them blind, purely on rigour, insight, "
            "evidence and truthfulness. Do not show favouritism."
        )
        user = (
            f"Positions:\n\n{anon_block}\n\n"
            f"Return ONLY compact JSON, no prose: {{\"rankings\": [best-to-worst list of the letters {letter_list}], "
            f"\"most_convincing\": \"<one letter>\"}}."
        )
        try:
            raw = await generate(reviewer, system, user, max_tokens=200)
            return _parse_json(raw)
        except Exception as e:
            logger.warning(f"Review failed for {reviewer['name']}: {e}")
            return None

    results = await asyncio.gather(*[review_one(r) for r in participants])
    for data in results:
        if not data:
            continue
        ranks = [r for r in data.get("rankings", []) if r in borda]
        for idx, l in enumerate(ranks):
            borda[l] += (n - 1 - idx)
        mc = data.get("most_convincing")
        if mc in votes:
            votes[mc] += 1

    max_b = max(borda.values()) or 1
    standings = []
    for l, pos in letter_to_pos.items():
        m = pos["member"]
        standings.append({
            "member_id": m["id"], "name": m["name"], "color": m["color"],
            "stance": pos["text"], "raw_score": borda[l],
            "score": round(100 * borda[l] / max_b), "votes": votes[l],
        })
    standings.sort(key=lambda x: (-x["raw_score"], -x["votes"]))
    mvp = max(standings, key=lambda x: x["votes"]) if standings else None
    return {
        "generated_at": now_iso(),
        "standings": standings,
        "mvp_id": mvp["member_id"] if mvp and mvp["votes"] > 0 else None,
        "mvp_name": mvp["name"] if mvp and mvp["votes"] > 0 else None,
    }


@api_router.post("/sessions/{sid}/review")
async def peer_review(sid: str, user: User = Depends(get_current_user), _rl: None = Depends(rate_limit)):
    doc = await db.sessions.find_one({"id": sid, "owner": user.user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")
    participants = [await resolved_member(p) for p in doc["participant_ids"]]
    review = await _compute_review(participants, doc["turns"])
    await db.sessions.update_one({"id": sid, "owner": user.user_id}, {"$set": {"review": review}})
    return review


class SynthesizeRequest(BaseModel):
    chairman_id: str
    question: Optional[str] = Field(None, max_length=4000)


@api_router.post("/sessions/{sid}/synthesize")
async def synthesize(sid: str, body: SynthesizeRequest, user: User = Depends(get_current_user), _rl: None = Depends(rate_limit)):
    doc = await db.sessions.find_one({"id": sid, "owner": user.user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")
    if body.chairman_id not in MEMBERS_BY_ID:
        raise HTTPException(status_code=400, detail="Unknown chairman")
    participants = [await resolved_member(p) for p in doc["participant_ids"]]

    new_turns = []
    if body.question and body.question.strip():
        q_turn = {"id": str(uuid.uuid4()), "speaker_id": "human", "speaker_name": "You",
                  "color": "#ffffff", "text": body.question.strip(), "ts": now_iso()}
        new_turns.append(q_turn)

    question = (body.question or "").strip() or doc["title"]

    async def answer_one(member):
        system = (
            f"You are {member['name']} from {member['org']}. Answer the question below independently with your own "
            "best thinking — you are NOT seeing other models' answers. Be substantive, accurate and well-reasoned. "
            "Write in clear prose (no markdown headings, bullet lists, or code fences)."
        )
        if member.get("persona"):
            system += f" Persona: {member['persona']}"
        try:
            txt = await generate(member, system, f"Question: {question}", max_tokens=600)
        except HTTPException:
            raise
        except Exception as e:
            txt = f"(no answer — {str(e)[:120]})"
        return {"id": str(uuid.uuid4()), "speaker_id": member["id"], "speaker_name": member["name"],
                "color": member["color"], "text": txt, "ts": now_iso()}

    answers = await asyncio.gather(*[answer_one(m) for m in participants])
    answer_turns = list(answers)
    all_new = new_turns + answer_turns

    # Blind peer review over the fresh answers
    try:
        review = await _compute_review(participants, answer_turns)
    except HTTPException:
        review = None

    # Chairman synthesis
    chair = await resolved_member(body.chairman_id)
    labeled = "\n\n".join([f"{a['speaker_name']}: {a['text']}" for a in answer_turns])
    rank_summary = ""
    if review:
        rank_summary = "\n\nBlind peer-review ranking (best first): " + ", ".join(
            [f"{s['name']} ({s['score']}/100, {s['votes']} votes)" for s in review["standings"]])
    chair_system = (
        f"You are {chair['name']}, the Council Chairman. Synthesise the members' independent answers into ONE "
        "authoritative, well-structured answer to the question. Integrate the strongest points, resolve conflicts, "
        "and explicitly note any important dissent. Attribute key insights to members by name where useful. "
        "Be clear and decisive."
    )
    chair_user = f"Question: {question}\n\nIndependent answers:\n\n{labeled}{rank_summary}\n\nWrite the synthesised council answer now."
    synth_text = await generate(chair, chair_system, chair_user, max_tokens=1100)

    synthesis = {"question": question, "text": synth_text, "chairman_id": chair["id"],
                 "chairman_name": chair["name"], "chairman_color": chair["color"], "ts": now_iso()}

    update = {"$push": {"turns": {"$each": all_new}}, "$set": {"synthesis": synthesis}}
    if review:
        update["$set"]["review"] = review
    await db.sessions.update_one({"id": sid, "owner": user.user_id}, update)
    return {"answers": all_new, "review": review, "synthesis": synthesis}


class TTSRequest(BaseModel):
    text: str = Field(..., max_length=8000)
    member_id: Optional[str] = None
    voice: Optional[str] = None


@api_router.post("/tts")
async def synth_voice(body: TTSRequest, user: User = Depends(get_current_user), _rl: None = Depends(rate_limit)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=400, detail="Voice key not configured")
    voice = body.voice
    if not voice and body.member_id in MEMBERS_BY_ID:
        voice = MEMBERS_BY_ID[body.member_id]["voice"]
    voice = voice or "alloy"
    try:
        tts = OpenAITextToSpeech(api_key=EMERGENT_LLM_KEY)
        audio = await tts.generate_speech_base64(text=body.text[:4000], model="tts-1", voice=voice)
        return {"audio_base64": audio}
    except Exception as e:
        logger.warning(f"TTS failed: {e}")
        raise HTTPException(status_code=500, detail="Voice generation failed")


@api_router.get("/sessions/{sid}/export")
async def export_pdf(sid: str, user: User = Depends(get_current_user)):
    doc = await db.sessions.find_one({"id": sid, "owner": user.user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, HRFlowable)
    from xml.sax.saxutils import escape

    buf = BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, topMargin=22 * mm, bottomMargin=18 * mm,
                            leftMargin=20 * mm, rightMargin=20 * mm, title=doc["title"])
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=22, textColor=colors.HexColor("#111111"), spaceAfter=4)
    meta = ParagraphStyle("meta", parent=ss["Normal"], fontSize=9, textColor=colors.HexColor("#888888"))
    sec = ParagraphStyle("sec", parent=ss["Heading2"], fontSize=13, textColor=colors.HexColor("#111111"),
                         spaceBefore=16, spaceAfter=6)
    body = ParagraphStyle("body", parent=ss["Normal"], fontSize=10.5, leading=15, textColor=colors.HexColor("#222222"))
    small = ParagraphStyle("small", parent=ss["Normal"], fontSize=9, leading=13, textColor=colors.HexColor("#555555"))

    participants = [await resolved_member(p) for p in doc["participant_ids"]]
    story = [Paragraph(escape(doc["title"]), h1)]
    names = ", ".join([f"{m['name']} ({m['org']})" for m in participants])
    story.append(Paragraph(f"THE COUNCIL &nbsp;·&nbsp; {escape(names)}", meta))
    story.append(Paragraph(f"Status: {doc.get('status', 'active')} &nbsp;·&nbsp; {len(doc.get('turns', []))} turns", meta))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#dddddd")))

    if doc.get("conclusion"):
        story.append(Paragraph("Final Verdict", sec))
        story.append(Paragraph(f"<i>Drafted by {escape(doc['conclusion']['drafter_name'])}</i>", small))
        for para in doc["conclusion"]["text"].split("\n"):
            if para.strip():
                story.append(Paragraph(escape(para.strip()), body))
                story.append(Spacer(1, 4))

    rv = doc.get("review")
    if rv and rv.get("standings"):
        story.append(Paragraph("Council Standings (blind peer review)", sec))
        for i, s in enumerate(rv["standings"]):
            tag = "  ★ Most convincing" if s["member_id"] == rv.get("mvp_id") else ""
            story.append(Paragraph(
                f"<b>{i + 1}. {escape(s['name'])}</b> — score {s['score']}/100 · {s['votes']} vote(s){tag}", small))
        story.append(Spacer(1, 4))

    if doc.get("notes"):
        story.append(Paragraph("Scribe's Notes", sec))
        for nte in doc["notes"]:
            story.append(Paragraph(f"• {escape(nte['text'])}", body))

    story.append(Paragraph("Full Transcript", sec))
    for t in doc.get("turns", []):
        c = t.get("color", "#000000")
        story.append(Paragraph(f'<font color="{c}"><b>{escape(t["speaker_name"])}</b></font>', small))
        story.append(Paragraph(escape(t["text"]), body))
        story.append(Spacer(1, 6))

    pdf.build(story)
    buf.seek(0)
    fname = "".join(ch for ch in doc["title"] if ch.isalnum() or ch in " -_")[:40].strip() or "council"
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{fname}.pdf"'})


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origin_regex=".*",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
