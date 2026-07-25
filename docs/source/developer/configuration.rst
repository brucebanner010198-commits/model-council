Configuration
=============

All configuration comes from environment variables — nothing is hardcoded.

Backend (``backend/.env``)
--------------------------

.. list-table::
   :header-rows: 1
   :widths: 30 15 55

   * - Variable
     - Required
     - Description
   * - ``MONGO_URL``
     - yes
     - MongoDB connection string.
   * - ``DB_NAME``
     - yes
     - Database name. Do not change casually — data is keyed to it.
   * - ``CORS_ORIGINS``
     - no
     - Comma-separated origins (the app uses an origin-echoing regex with credentials).
   * - ``EMERGENT_LLM_KEY``
     - yes (voice)
     - Powers OpenAI TTS + Whisper for voice.
   * - ``OPENROUTER_API_KEY``
     - no
     - Global OpenRouter fallback. Users can also set their own in Settings.
   * - ``OPENAI_API_KEY`` … ``MOONSHOT_API_KEY``
     - no
     - Optional server-level provider fallbacks (per-user keys take precedence).
   * - ``RESEND_API_KEY``
     - no
     - Enables magic-link email delivery. Empty → ``/auth/magic/request`` returns 503.
   * - ``SENDER_EMAIL``
     - no
     - "From" address for magic-link emails (default ``onboarding@resend.dev``).
   * - ``RATE_LIMIT``
     - no
     - Requests/min per IP on expensive endpoints (default ``60``).
   * - ``APP_BASE_URL``
     - no
     - Fallback base URL for building magic-link URLs when no ``Origin`` header is present.

Frontend (``frontend/.env``)
----------------------------

.. list-table::
   :header-rows: 1
   :widths: 30 15 55

   * - Variable
     - Required
     - Description
   * - ``REACT_APP_BACKEND_URL``
     - yes
     - Base URL for all API calls. The frontend must never use a hardcoded URL.

Rules of the road
-----------------

* **Never** commit ``.env`` files or hardcode secrets/URLs/ports.
* Add new variables; never remove the protected ones (``MONGO_URL``, ``DB_NAME``,
  ``REACT_APP_BACKEND_URL``).
* After changing ``.env`` or installing dependencies, restart the affected service:

  .. code-block:: bash

     sudo supervisorctl restart backend
     sudo supervisorctl restart frontend

Per-user keys vs. env keys
--------------------------

Keys entered in the in-app **Settings** dialog are stored per user (in the ``settings``
collection, ``_id = user_id``) and always take precedence over the corresponding
environment fallback.
