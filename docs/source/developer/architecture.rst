Architecture
============

High-level flow
---------------

.. code-block:: text

   Browser (React SPA)
     │  REACT_APP_BACKEND_URL + "/api/..."
     ▼
   Kubernetes Ingress ──/api──▶ FastAPI (:8001)
                          │
                          ├── MongoDB (Motor)            # users, sessions, settings, ...
                          ├── Provider APIs / OpenRouter # model completions
                          ├── emergentintegrations       # OpenAI TTS + Whisper (voice)
                          └── Resend                     # magic-link emails

* The frontend never calls providers directly; everything goes through the backend.
* All backend routes are mounted under an ``/api`` prefix (required for ingress routing).
* Backend binds ``0.0.0.0:8001``; frontend serves on ``3000``. Both are supervisor-managed.

Model routing (the core idea)
------------------------------

Every completion goes through a single ``generate(member, system, user, max_tokens)``
helper that implements **per-model, subscription-first routing with OpenRouter fallback**:

.. code-block:: text

   routing preference for member:
     "openrouter" → [OpenRouter]
     "direct"     → [native provider, then OpenRouter on error]
     "auto"       → [native provider if key present, else OpenRouter]

   for route in routes:
       try: return call(route)          # native = OpenAI-compatible POST /chat/completions
       except: remember error, continue
   raise graceful 4xx/5xx

Native providers are all called through one OpenAI-compatible client
(``call_openai_compatible``) using per-provider base URLs:

.. list-table::
   :header-rows: 1

   * - Provider
     - Base URL
   * - OpenAI
     - ``https://api.openai.com/v1``
   * - Anthropic
     - ``https://api.anthropic.com/v1``
   * - Google Gemini
     - ``https://generativelanguage.googleapis.com/v1beta/openai``
   * - DeepSeek
     - ``https://api.deepseek.com/v1``
   * - Moonshot (Kimi)
     - ``https://api.moonshot.ai/v1``

The OpenRouter fallback uses ``https://openrouter.ai/api/v1``.

Per-request user context
-------------------------

``get_current_user`` (a FastAPI dependency) authenticates the request and stores the
user id in a :class:`contextvars.ContextVar` (``_current_user_id``). Settings helpers
(``get_settings``, ``get_provider_key``, ``get_openrouter_key``) read that contextvar, so
they resolve the **current user's** keys/routing without threading ``user_id`` through
every call site.

.. warning::

   Because it relies on a ContextVar, never call those settings helpers from a background
   task that isn't part of a request whose ``get_current_user`` has run — pass ``user_id``
   explicitly there instead.

Voice pipeline
--------------

* **TTS:** ``OpenAITextToSpeech.generate_speech_base64(text, model="tts-1", voice=...)`` —
  each member has a distinct voice. Returned as base64 and played in the browser.
* **STT:** ``OpenAISpeechToText.transcribe(file, model="whisper-1")`` — the ``/api/stt``
  endpoint accepts a size-capped, type-checked audio upload.

Cost-abuse protection
----------------------

* Per-IP sliding-window **rate limiting** (``RATE_LIMIT``/min, default 60) on expensive
  endpoints (respond, notes, conclude, review, synthesize, tts, stt, magic-request).
* Request **size caps** via Pydantic ``Field(max_length=...)`` and a 25 MB audio cap.
* Authentication gates every data endpoint; data is isolated per user.
