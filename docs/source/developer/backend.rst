Backend Walkthrough
===================

The backend is a **single FastAPI file**. ``backend/server.py`` is ~970 lines,
plus a small pytest suite under ``backend/tests/``. Keeping it in one file is a
deliberate choice for this MVP: everything a maintainer touches (auth, model
routing, voice, PDF export) is discoverable in one place.

.. code-block:: text

   backend/
   ├── server.py         # FastAPI app, all routes, model routing, voice, PDF
   ├── requirements.txt  # pinned Python deps
   ├── pytest.ini        # xdist config for parallel tests
   └── tests/
       ├── conftest.py
       ├── test_auth_gating.py
       ├── test_isolation.py
       ├── test_magic_link.py
       ├── test_providers.py
       └── backend_test.py

Structure of ``server.py``
--------------------------

Reading top-to-bottom you'll hit these logical sections:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Section
     - What it contains
   * - **Bootstrap**
     - ``load_dotenv``, MongoDB client (``motor``), ``EMERGENT_LLM_KEY``,
       Resend init, FastAPI app + ``/api`` router, logger.
   * - **Provider registry**
     - ``PROVIDERS`` dict. OpenAI-compatible base URLs for OpenAI, Anthropic,
       Gemini, DeepSeek, Moonshot.
   * - **Council roster**
     - ``COUNCIL`` list (5 members: id, name, org, colour, voice, provider,
       ``native_model``, ``model``) and ``NOTETAKER`` (the Scribe).
   * - **Auth**
     - ``get_current_user`` (cookie or ``Authorization: Bearer``), the
       ``_current_user_id`` ContextVar, Emergent OAuth exchange, magic-link
       request/verify (Resend + SHA-256 hashed tokens).
   * - **Rate limiting**
     - Sliding-window per-IP bucket, applied via ``Depends(rate_limit)`` on
       expensive endpoints. Env var ``RATE_LIMIT`` (default ``60``/min).
   * - **Settings helpers**
     - ``get_settings`` / ``get_provider_key`` / ``get_openrouter_key`` /
       ``resolved_member``. All read the current user's overrides from the
       ``settings`` collection.
   * - **Model routing**
     - ``call_openai_compatible`` (one HTTP call for every native provider),
       ``call_openrouter`` (fallback), and the unified ``generate()`` helper.
   * - **Prompt building**
     - ``build_persona_prompt``, ``transcript_text``.
   * - **Routes**
     - ``/api/auth/*``, ``/api/council``, ``/api/settings``,
       ``/api/openrouter/models``, ``/api/sessions*``, ``/api/stt``,
       ``/api/tts``, ``/api/sessions/{sid}/export``.
   * - **Peer review / Synthesize**
     - ``_compute_review`` (Borda + "most convincing") and the
       ``/synthesize`` orchestration.
   * - **PDF export**
     - ``reportlab`` builds an A4 PDF from the session's turns, notes,
       standings and verdict.
   * - **Middleware & lifecycle**
     - Permissive origin-echoing CORS with credentials; ``shutdown_db_client``.

The generate() helper
---------------------

Every LLM completion. A member's turn, the Scribe's notes, the conclusion, a
peer review, a synthesise answer. Goes through :py:func:`generate`:

.. code-block:: python

   text = await generate(member, system_prompt, user_prompt, max_tokens=400)

It picks one of three route lists based on the member's ``routing`` setting
(``auto``, ``direct``, ``openrouter``), tries each in order, and raises a clean
HTTP error only if *all* routes fail. See :doc:`architecture` for the diagram.

.. important::

   When adding a new model call, **always** go through ``generate()``. Don't
   call providers directly. You'd bypass the fallback, the ContextVar-based
   per-user key lookup, and the error normalisation.

Adding a new endpoint
---------------------

1. Define a Pydantic ``BaseModel`` for the request body (put ``max_length`` on
   free-text fields. This is the abuse guard).
2. Register the route on ``api_router`` (never on ``app`` directly. You'd miss
   the ``/api`` prefix).
3. Add ``user: User = Depends(get_current_user)`` unless it's a truly public
   route (only ``/api/`` and the auth exchange endpoints qualify today).
4. For anything that calls an LLM, add ``_rl: None = Depends(rate_limit)``.
5. Persist to Mongo scoped to ``{"owner": user.user_id}``. Never return
   ``_id`` (use ``{"_id": 0}`` projections or ``.pop("_id", None)``).
6. Add a test in ``backend/tests/`` for at least the happy path and the
   401/404/400 boundaries.

Adding a new council member
---------------------------

Edit ``COUNCIL`` in ``server.py``:

.. code-block:: python

   {"id": "newbie", "name": "NewModel 1", "org": "Acme", "country": "US",
    "open": False, "specialty": "…", "color": "#22d3ee", "voice": "shimmer",
    "provider": "openai",                     # must be a key in PROVIDERS
    "native_model": "newmodel-1",             # provider-side model id
    "model": "openai/newmodel-1"},            # OpenRouter fallback id

Then:

* If it's a **new provider** (not in ``PROVIDERS``), add its OpenAI-compatible
  base URL there.
* Add an entry in the user guide (:doc:`../user/index`) and, if the model
  needs a matching voice, pick one of the OpenAI TTS voices (``alloy``,
  ``echo``, ``fable``, ``onyx``, ``nova``, ``sage``, ``shimmer``).

Voice pipeline
--------------

* **TTS**. :class:`emergentintegrations.llm.openai.OpenAITextToSpeech` with
  ``model="tts-1"`` and the member's ``voice``. The endpoint returns
  ``audio_base64`` and the browser plays it.
* **STT**. :class:`emergentintegrations.llm.openai.OpenAISpeechToText` with
  ``whisper-1``. The endpoint enforces a **25 MB** upload cap and a whitelist
  of audio MIME types (see ``ALLOWED_AUDIO``).

Both use the ``EMERGENT_LLM_KEY`` env variable. No per-user key is required
for voice.

PDF export
----------

``GET /api/sessions/{sid}/export`` builds an in-memory PDF with
``reportlab.platypus`` and streams it back with a filename derived from the
session title. It includes (in order): title + participants, final verdict,
Council Standings, Scribe's notes, and the full transcript with per-speaker
colouring.
