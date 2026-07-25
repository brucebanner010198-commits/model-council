from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import asyncio
import tempfile
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
import json
import random
from io import BytesIO
from datetime import datetime, timezone
import httpx
from fastapi.responses import StreamingResponse

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
            raw = await call_openrouter(reviewer["model"], [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ], max_tokens=200)
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
async def peer_review(sid: str):
    doc = await db.sessions.find_one({"id": sid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")
    participants = [await resolved_member(p) for p in doc["participant_ids"]]
    review = await _compute_review(participants, doc["turns"])
    await db.sessions.update_one({"id": sid}, {"$set": {"review": review}})
    return review


class SynthesizeRequest(BaseModel):
    chairman_id: str
    question: Optional[str] = None


@api_router.post("/sessions/{sid}/synthesize")
async def synthesize(sid: str, body: SynthesizeRequest):
    doc = await db.sessions.find_one({"id": sid}, {"_id": 0})
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
            txt = await call_openrouter(member["model"], [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Question: {question}"},
            ], max_tokens=600)
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
    synth_text = await call_openrouter(chair["model"], [
        {"role": "system", "content": chair_system},
        {"role": "user", "content": chair_user},
    ], max_tokens=1100)

    synthesis = {"question": question, "text": synth_text, "chairman_id": chair["id"],
                 "chairman_name": chair["name"], "chairman_color": chair["color"], "ts": now_iso()}

    update = {"$push": {"turns": {"$each": all_new}}, "$set": {"synthesis": synthesis}}
    if review:
        update["$set"]["review"] = review
    await db.sessions.update_one({"id": sid}, update)
    return {"answers": all_new, "review": review, "synthesis": synthesis}


class TTSRequest(BaseModel):
    text: str
    member_id: Optional[str] = None
    voice: Optional[str] = None


@api_router.post("/tts")
async def synth_voice(body: TTSRequest):
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
async def export_pdf(sid: str):
    doc = await db.sessions.find_one({"id": sid}, {"_id": 0})
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
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
