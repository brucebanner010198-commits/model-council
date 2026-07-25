# PRD — The Council (AI Model Council)

## Original Problem Statement
A "model council" of frontier models where a human is a member. Human and models talk to each other in natural language, have critical discussions, and any conversation runs until a conclusion is drafted by a model the user assigns. Zoom-call style UI (each model on the other end). Real spoken voice. A dedicated note-taker model captures key points separate from the recorded transcript. Conversations saved with each speaker's (model) name.

## User Choices
- Real voice — models speak out loud with distinct voices.
- Council of top 5 models by latest LiveBench (US paid + China open), each #1 at some task.
- Optional personas; default to each model's natural personality.
- Single-user personal workspace (no login for now).
- Dedicated always-on note-taker (Scribe) + user-assigned conclusion drafter.

## Architecture
- **Frontend**: React 19, Tailwind, framer-motion, shadcn/ui, sonner. Pages: Home (dashboard + convene + archive), Room (Zoom-style call). Dark "Mission Control" theme (Cabinet Grotesk / IBM Plex Sans / JetBrains Mono).
- **Backend**: FastAPI + MongoDB (motor). Council text via **OpenRouter** (user's own key). Voice via **emergentintegrations** OpenAI TTS (`tts-1`) + Whisper STT (`whisper-1`) on the built-in EMERGENT_LLM_KEY.
- **Council (editable model IDs)**: GPT-5.6 (openai/gpt-5.6), Claude Opus 5 (anthropic/claude-opus-4.6), Gemini 3.1 Pro (google/gemini-3-pro-preview), DeepSeek V4 Pro (deepseek/deepseek-chat, open), Kimi K3 (moonshotai/kimi-k2, open). Scribe note-taker (openai/gpt-4o-mini). Each has a distinct voice + accent color.

## Implemented (2026-06)
- Home: hero, standing council roster, session archive (open/delete), Settings dialog (paste OpenRouter key, edit per-member model IDs + personas, Scribe model). Convene dialog (topic + member chips) → creates session, navigates to Room.
- Room: Zoom-style video tiles (active-speaker glow + framer-motion waveform, thinking state), human tile with mic state, live transcript panel (speaker name + color), separate Scribe notes panel, conclusion/verdict block. Control dock: mic push-to-record → Whisper STT into input, address council (round table), open the floor (models initiate), refresh notes, draft conclusion (pick drafter), mute voices, leave.
- Turn engine: human message + sequential model responses, each spoken via TTS (auto-plays with active-speaker highlight), auto note refresh after each round.
- Voice pipeline verified end-to-end (TTS→STT round-trip). Settings persistence verified. Graceful 400 when OpenRouter key absent.
- Backend pytest suite (8/8) + frontend E2E (100%) passing.

## Backlog
- P1: streaming token-by-token; auto-open Settings when key missing.
- P2: auth/multi-user, sharable links, live mic VAD/barge-in.
- P2: read HTTP-Referer from env; per-session persona overrides.

## Differentiators shipped (beats market councils)
- **Live spoken Zoom-style council** with distinct per-model voices + on-demand replay (beyond Karpathy's text-only LLM Council).
- **Auto-debate**: models argue autonomously for N rounds (stoppable).
- **Blind peer-review "Council Standings"**: anonymous cross-ranking → Borda score + most-convincing MVP (Karpathy-style, visualised).
- **Synthesize answer (additive, Perplexity-style)**: same question fanned to all 5 models in parallel → blind review → a chosen Chairman merges into one authoritative answer. Separate button; does not affect the live council/debate flow.
- **One-click PDF export** (transcript + Scribe notes + standings + verdict) via reportlab.
- Dedicated always-on Scribe note-taker; assignable conclusion drafter; personas; editable model IDs.

## Model routing (subscription-first)
- Each council model runs on the user's own **provider subscription/API key** (OpenAI, Anthropic, Google Gemini, DeepSeek, Moonshot/Kimi) via native OpenAI-compatible endpoints.
- **OpenRouter is a per-model fallback** — used only for the specific model whose subscription key is missing or errors.
- Per-model routing choice in Settings: `auto` (subscription→OpenRouter) | `direct` | `openrouter`. Editable native + OpenRouter model IDs per member.
- Keys stored server-side, never returned by the API (verified, 27/27 backend tests).

## Next Tasks
1. User adds provider subscription key(s) and/or an OpenRouter key in Settings to activate live flows.
2. (Offered) Add authentication (JWT or Emergent Google login) before sharing — closes the cost-abuse vector properly.
