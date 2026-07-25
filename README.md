# The Council 🏛️

> A live, spoken roundtable where the world's frontier AI models — **GPT, Claude, Gemini, DeepSeek and Kimi** — debate your ideas out loud, challenge each other like real experts, and draft a final verdict. You hold the chair.

The Council is a Zoom-style "AI model council": a human convenes a panel of frontier LLMs that talk in **real voice** (distinct per model), have critical natural-language discussions, take notes, cross-review each other, and produce a written conclusion. It also includes a Perplexity-style **Synthesize** mode (fan one question to all models → blind peer-review → a Chairman merges one authoritative answer).

---

## ✨ Features

- **Zoom-style council chamber** — video tiles per model with active-speaker glow, live waveforms and "thinking" states.
- **Real voices** — each model speaks aloud (OpenAI TTS); you speak back via microphone (Whisper STT).
- **Live turn-taking** — *Open the floor*, *Round table*, or address a specific member; models can initiate.
- **Auto-debate** — models argue autonomously for N rounds (stoppable).
- **Blind peer-review "Council Standings"** — members anonymously cross-rank each other (Borda score + "most convincing" MVP).
- **Synthesize (Perplexity-beater)** — same question → all models answer in parallel → blind review → Chairman synthesis.
- **Dedicated Scribe** — an always-on note-taker capturing key points, separate from the transcript.
- **Assignable Conclusion drafter** — pick a model to write the final verdict.
- **One-click PDF export** — transcript + Scribe notes + standings + verdict.
- **Bring-your-own models** — each model runs on **your provider subscription/API key** (OpenAI, Anthropic, Google, DeepSeek, Moonshot), with **per-model OpenRouter fallback**.
- **Multi-user auth** — Emergent **Google login** *and* passwordless **email magic-link**, merged by email. Per-user private sessions & keys.

---

## 🧱 Tech Stack

| Layer      | Technology |
|------------|------------|
| Frontend   | React 19, React Router, Tailwind CSS, shadcn/ui, framer-motion, sonner |
| Backend    | FastAPI, Motor (async MongoDB) |
| Database   | MongoDB |
| Voice      | OpenAI TTS (`tts-1`) + Whisper (`whisper-1`) via `emergentintegrations` |
| Models     | Native OpenAI-compatible provider APIs + OpenRouter fallback |
| Email      | Resend (magic-link sign-in) |
| Docs       | Sphinx (Furo theme) |

---

## 🚀 Quick Start

Both services run under **supervisor** in this environment.

```bash
# Backend deps
cd backend && pip install -r requirements.txt

# Frontend deps
cd frontend && yarn install

# Restart services after env/dep changes
sudo supervisorctl restart backend frontend
```

- Frontend: served on port `3000`
- Backend: served on port `8001`, all routes prefixed with `/api`
- Frontend talks to the backend **only** via `REACT_APP_BACKEND_URL`

### Minimum configuration to go live
1. **Sign in** works out of the box with Google. For magic-link emails, set `RESEND_API_KEY` + `SENDER_EMAIL` in `backend/.env`.
2. **Add model keys** in the in-app **Settings** dialog: one or more provider subscription keys and/or an OpenRouter fallback key.
3. **Voice** works via the built-in `EMERGENT_LLM_KEY`.

---

## 🔑 Environment Variables

### `backend/.env`
| Variable | Purpose |
|----------|---------|
| `MONGO_URL` | MongoDB connection string (required) |
| `DB_NAME` | Database name (required) |
| `CORS_ORIGINS` | Allowed CORS origins |
| `EMERGENT_LLM_KEY` | Powers voice (TTS/STT) |
| `OPENROUTER_API_KEY` | Global OpenRouter fallback (users can also set their own in Settings) |
| `OPENAI/ANTHROPIC/GEMINI/DEEPSEEK/MOONSHOT_API_KEY` | Optional server-level provider fallbacks |
| `RESEND_API_KEY`, `SENDER_EMAIL` | Magic-link email delivery |
| `RATE_LIMIT` | Requests/min per IP on expensive endpoints (default 60) |

### `frontend/.env`
| Variable | Purpose |
|----------|---------|
| `REACT_APP_BACKEND_URL` | Base URL for all API calls |

> ⚠️ Never hardcode URLs, ports or secrets. All come from environment variables.

---

## 📚 Documentation

Full documentation lives in [`/docs`](./docs) and is written for **two audiences**:

- **User Guide** — how to sign in, convene a council, talk to the models, run debates, synthesize answers, and export verdicts.
- **Developer / Maintainer Guide** — architecture, API reference, auth internals, configuration, testing and deployment.

Build it locally:

```bash
cd docs
pip install -r requirements.txt
make html
# open docs/build/html/index.html
```

---

## 🗂️ Project Structure

```
/app
├── backend/            # FastAPI app (server.py), requirements.txt, .env
├── frontend/           # React app (src/), package.json, .env
├── docs/               # Sphinx documentation (user + developer guides)
├── memory/             # PRD.md, test_credentials.md
├── auth_testing.md     # How to seed auth sessions for testing
└── README.md
```

---

## 🔒 Security Notes

- Every `/api` route (except health check and the auth exchange endpoints) requires a valid session.
- Data is **isolated per user** (`sessions.owner`, `settings._id = user_id`).
- Provider/API keys are stored server-side and **never returned** by the API.
- Basic per-IP rate limiting + request-size caps protect against cost abuse.

---

## 📄 License

Proprietary — all rights reserved unless stated otherwise.
