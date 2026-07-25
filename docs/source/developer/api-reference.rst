API Reference
=============

All backend routes are prefixed with ``/api``. Unless noted, every endpoint
requires a valid session (``session_token`` cookie **or**
``Authorization: Bearer <token>``). Unauthenticated requests get **401**.

.. contents::
   :local:
   :depth: 1

Conventions
-----------

* All IDs are UUID-v4 strings (never Mongo ``ObjectId``).
* All timestamps are ISO-8601 UTC strings.
* Errors follow FastAPI's ``{"detail": "..."}`` shape.
* Expensive endpoints are rate-limited per IP (``RATE_LIMIT`` req/min,
  default 60). Exceeding it returns **429**.
* Free-text request fields have a ``max_length``; oversized bodies get **422**.

Health
------

.. http:get:: /api/

   Liveness probe.

   **Auth**: none. **Response 200**:

   .. code-block:: json

      {"message": "AI Model Council API"}

Authentication
--------------

.. http:post:: /api/auth/session

   Exchange an Emergent OAuth ``session_id`` for a session cookie.

   **Body**: ``{"session_id": "<opaque>"}`` — this is issued by the Emergent
   OAuth redirect (Google login).

   **Response 200**: user profile ``{user_id, email, name, picture}``. Sets a
   secure ``session_token`` cookie (SameSite=None, HttpOnly, 7-day TTL).

.. http:post:: /api/auth/magic/request

   Send a passwordless sign-in link.

   **Body**: ``{"email": "user@example.com"}``.

   **Effect**: stores an SHA-256 hash of a fresh 32-byte URL-safe token in
   ``magic_links``, then emails a link ``<Origin>/login#magic=<token>`` via
   Resend. The link is **single-use** and expires in **15 minutes**.

   Rate-limited. Returns **503** if ``RESEND_API_KEY`` is not set.

.. http:post:: /api/auth/magic/verify

   Redeem a magic-link token.

   **Body**: ``{"token": "<from-email-hash>"}``.

   **Response 200**: user profile (same shape as
   ``/auth/session``). Marks the token used and sets the session cookie.

.. http:get:: /api/auth/me

   Return the currently signed-in user (``User`` model).

.. http:post:: /api/auth/logout

   Delete the current session from Mongo and clear the cookie. Idempotent.

Council & settings
------------------

.. http:get:: /api/council

   Return the roster (with each user's overrides applied), the Scribe,
   configured provider status flags, and whether an OpenRouter fallback is
   configured.

.. http:get:: /api/settings

   Return the current user's non-secret settings — booleans for configured
   keys, plus ``models``, ``native_models``, ``routing``, ``personas``,
   ``notetaker_model``. **Actual key values are never returned.**

.. http:post:: /api/settings

   Update the current user's settings. All fields optional; only sent fields
   are patched.

   **Body** (any subset): ``openrouter_key``, ``provider_keys``, ``models``,
   ``native_models``, ``routing``, ``personas``, ``notetaker_model``.

.. http:get:: /api/openrouter/models

   Proxy list of OpenRouter model IDs, used by the Settings dialog for
   autocomplete. Requires an OpenRouter key.

Sessions
--------

.. http:post:: /api/sessions

   Create a new council session.

   **Body**: ``{"title": "...", "participant_ids": ["gpt", "claude", ...]}``.

   Unknown IDs are silently dropped. Returns the created session document.

.. http:get:: /api/sessions

   List the current user's sessions (newest first, 200 max). Each includes a
   ``turn_count`` for the dashboard.

.. http:get:: /api/sessions/{sid}

   Full session document (including ``turns``, ``notes``, ``review``,
   ``conclusion``, ``synthesis``).

.. http:delete:: /api/sessions/{sid}

   Delete a session owned by the current user. Idempotent.

.. http:post:: /api/sessions/{sid}/message

   Append a human turn to the session.

   **Body**: ``{"text": "..."}``. Returns the created turn.

.. http:post:: /api/sessions/{sid}/respond

   Have a specific member speak next.

   **Body**: ``{"model_id": "gpt", "directive": "optional steering prompt"}``.

   **Response**: ``{"turn": {...}, "audio_base64": "..."}`` — a new turn is
   appended and TTS audio is returned inline. Rate-limited.

.. http:post:: /api/sessions/{sid}/notes

   Regenerate the Scribe's key-points list. Rate-limited.

.. http:post:: /api/sessions/{sid}/conclude

   Ask a specific member to draft the final written verdict.

   **Body**: ``{"drafter_id": "claude"}``. Sets ``status="concluded"`` and
   ``conclusion={text, drafter_id, drafter_name, ts}``.

.. http:post:: /api/sessions/{sid}/review

   Run a blind peer review. Each member reads the others' *latest* turns
   anonymously and returns rankings + a "most convincing" vote. The route
   requires at least two members to have spoken.

   Returns ``{"standings": [...], "mvp_id", "mvp_name", "generated_at"}``.

.. http:post:: /api/sessions/{sid}/synthesize

   Perplexity-style one-shot answer: fan the question to all seated members
   in parallel, run a blind peer review over the answers, then have a
   Chairman merge them.

   **Body**: ``{"chairman_id": "gemini", "question": "optional; defaults to session title"}``.

   Appends the question (if provided) and all answers as turns; sets
   ``synthesis`` and (if possible) ``review``.

.. http:get:: /api/sessions/{sid}/export

   Stream an A4 PDF containing the session title, verdict, standings, notes
   and full transcript. ``Content-Disposition: attachment``.

Voice
-----

.. http:post:: /api/tts

   Synthesise a spoken clip via OpenAI TTS.

   **Body**: ``{"text": "...", "member_id": "gpt", "voice": "onyx"}`` — voice
   is inferred from ``member_id`` if not supplied. Returns
   ``{"audio_base64": "..."}``. Rate-limited.

.. http:post:: /api/stt

   Transcribe an uploaded audio file via Whisper.

   **Form field**: ``audio`` — multipart file. Max **25 MB**, MIME type must
   be in the ``ALLOWED_AUDIO`` whitelist (webm/ogg/mpeg/wav/mp4/m4a/…).

   Returns ``{"text": "..."}``. Rate-limited.

Status-code cheat sheet
-----------------------

.. list-table::
   :header-rows: 1
   :widths: 10 90

   * - Code
     - When
   * - 200
     - Success.
   * - 400
     - Bad body / unknown member / OpenRouter key missing when required.
   * - 401
     - No / invalid / expired session.
   * - 404
     - Session not owned by the caller (or doesn't exist).
   * - 413
     - Audio upload larger than 25 MB.
   * - 415
     - Unsupported audio MIME type.
   * - 422
     - Pydantic validation error (e.g. text exceeds ``max_length``).
   * - 429
     - Per-IP rate limit tripped.
   * - 502
     - Provider / OpenRouter upstream error (all routes exhausted).
   * - 503
     - Magic-link requested but ``RESEND_API_KEY`` not configured.
