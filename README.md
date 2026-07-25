# The Council

A live spoken roundtable of five frontier AI models. GPT, Claude, Gemini, DeepSeek and Kimi debate your ideas out loud, take notes, cross-review each other, and draft a final verdict. You hold the chair.

The Council is a video-call-style panel of large language models that talk in real voice (a distinct voice per model), hold natural-language discussions, and produce a written conclusion. It also includes a Synthesize mode: one question is sent to every model in parallel, the answers are blind peer-reviewed, and a Chairman merges them into a single answer.

---

## Features

- Council chamber with a video tile per model, active-speaker glow, live waveforms, and "thinking" states.
- Real voice for every model (OpenAI TTS) and speech-to-text for the user (Whisper).
- Turn-taking controls. Open the floor, run a round table, or address a specific member. Models can also initiate.
- Auto-debate for N rounds, stoppable at any time.
- Blind peer review with a Borda-scored leaderboard and a "most convincing" badge.
- Synthesize mode. One question, five parallel answers, blind review, then a Chairman drafts one answer.
- Dedicated Scribe model that keeps a running list of key points, separate from the transcript.
- Assignable conclusion drafter. Pick which model writes the final verdict.
- One-click PDF export with the transcript, Scribe notes, standings and verdict.
- Bring-your-own accounts. Every model runs on your own provider account. Options include a ChatGPT Plus / Pro or Claude Pro / Max subscription (experimental, personal-use only), per-provider API keys (OpenAI, Anthropic, Google, DeepSeek, Moonshot), or an OpenRouter key as universal fallback.
- Multi-user auth. Sign in with Google, with email and password, or with a magic-link email. All three flows merge to a single account by email address.

---

## Tech Stack

| Layer      | Technology |
|------------|------------|
| Frontend   | React 19, React Router, Tailwind CSS, shadcn/ui, framer-motion, sonner |
| Backend    | FastAPI, Motor (async MongoDB) |
| Database   | MongoDB |
| Voice      | OpenAI TTS (`tts-1`) and Whisper (`whisper-1`) via `emergentintegrations` |
| Models     | Native OpenAI-compatible provider APIs, subscription OAuth (Anthropic, OpenAI), OpenRouter fallback |
| Email      | Resend (optional, for magic-link sign-in) |
| Docs       | Sphinx with the Furo theme |

---

## Quick Start

Both services run under supervisor in the standard environment.

```bash
# Backend deps
cd backend && pip install -r requirements.txt

# Frontend deps
cd frontend && yarn install

# Restart services after env or dep changes
sudo supervisorctl restart backend frontend
```

- Frontend on port `3000`.
- Backend on port `8001`. All API routes are prefixed with `/api`.
- Frontend talks to the backend only via `REACT_APP_BACKEND_URL`.

### Minimum configuration to go live

1. Sign-in works out of the box with Google, or with email and password.
2. For magic-link sign-in, add `RESEND_API_KEY` and `SENDER_EMAIL` to `backend/.env`.
3. In the in-app Settings dialog, connect at least one option. A subscription (Claude Pro / Max, ChatGPT Plus / Pro), one or more provider API keys, or an OpenRouter key.
4. Voice works via the built-in `EMERGENT_LLM_KEY`. No extra setup.

---

## Environment Variables

### `backend/.env`

| Variable | Purpose |
|----------|---------|
| `MONGO_URL` | MongoDB connection string (required) |
| `DB_NAME` | Database name (required) |
| `CORS_ORIGINS` | Allowed CORS origins |
| `EMERGENT_LLM_KEY` | Powers voice (TTS and STT) |
| `OPENROUTER_API_KEY` | Global OpenRouter fallback. Users can also set their own in Settings |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `MOONSHOT_API_KEY` | Optional server-level provider fallbacks |
| `RESEND_API_KEY`, `SENDER_EMAIL` | Magic-link email delivery |
| `RATE_LIMIT` | Requests per minute per IP on expensive endpoints (default 60) |

### `frontend/.env`

| Variable | Purpose |
|----------|---------|
| `REACT_APP_BACKEND_URL` | Base URL for all API calls |

Never hardcode URLs, ports or secrets. Everything comes from environment variables.

---

## Documentation

Full documentation lives in [`/docs`](./docs) and is written for two audiences.

- User Guide. How to sign in, convene a council, talk to the models, run debates, synthesize answers, and export verdicts.
- Developer and Maintainer Guide. Architecture, API reference, auth internals, configuration, testing and deployment.

Build it locally:

```bash
cd docs
pip install -r requirements.txt
make html
# open docs/build/html/index.html
```

Once pushed to GitHub, the workflow at [`.github/workflows/docs.yml`](.github/workflows/docs.yml) builds the docs on every push and, from `main`, publishes them to GitHub Pages automatically. See [`docs/DEPLOY.md`](./docs/DEPLOY.md) for setup and Netlify or Vercel alternatives.

---

## Project Structure

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

## Security Notes

- Every `/api` route (except the health check and the auth exchange endpoints) requires a valid session.
- Data is isolated per user (`sessions.owner`, `settings._id = user_id`).
- Provider API keys and subscription tokens are stored server-side and are never returned by the API.
- Per-IP rate limiting and request-size caps protect against cost abuse.

---

## License

Proprietary. All rights reserved unless stated otherwise.
