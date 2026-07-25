Testing
=======

The backend ships with a **pytest** suite under ``backend/tests/`` that
exercises auth gating, per-user isolation, provider routing and the magic-link
lifecycle. The frontend uses **CRA's built-in Jest** (``yarn test``) for
component-level checks and delegates end-to-end validation to the platform's
UI testing agent (see :doc:`../developer/contributing`).

Backend tests
-------------

.. code-block:: text

   backend/
   ├── pytest.ini
   └── tests/
       ├── conftest.py            # shared fixtures (client, sessions, seed data)
       ├── test_auth_gating.py    # 401 on protected routes without a session
       ├── test_isolation.py      # user A cannot read/write user B's data
       ├── test_providers.py      # generate() route selection & fallback
       ├── test_magic_link.py     # request/verify happy path + replay & expiry
       └── backend_test.py        # broader smoke test against a running instance

Run them
~~~~~~~~

.. code-block:: bash

   cd backend
   pytest                         # parallelised (see pytest.ini: -n 2 --dist loadscope)
   pytest -n 0                    # force serial (do NOT use -p no:xdist, see note)
   pytest tests/test_magic_link.py -k verify   # a single test

.. note::

   ``pytest.ini`` pins ``-n 2 --dist loadscope`` (each test class/module runs
   on one worker). Tests share the running backend and assume sequential
   *intra-scope* state, so avoid changing these flags. To go serial use
   ``-n 0``, not ``-p no:xdist`` (which errors because addopts still passes
   ``-n``/``--dist``).

Writing a new backend test
~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Read ``conftest.py``. Most tests take a ``client`` fixture (an
   ``httpx.AsyncClient`` bound to the live backend URL) and a helper that
   creates a signed-in test user by inserting directly into ``users`` +
   ``user_sessions`` (see ``auth_testing.md``).
2. **Always** sign in as an isolated test user; never assume shared state.
3. Cover the boundary cases the endpoint actually enforces (401, 400, 422,
   413/415 for uploads, 429 for rate limits, 502 for provider fallthroughs).
4. Clean up rows you create (or scope them under a fresh ``user_id`` so they
   don't pollute other tests).

Frontend tests
--------------

The dependency stack (react-scripts / craco + jest) is preserved so
``yarn test`` runs, but the current suite is intentionally minimal. Flows
that need a real backend, real audio, or a real browser are covered by the
platform's UI testing agent instead.

When adding a component:

* Prefer isolating pure UI (buttons, dialogs, waveform math) as
  ``ComponentName.test.jsx`` next to the component.
* Mock ``lib/api.js`` when a test needs to assert HTTP behaviour without
  hitting the backend.

Manual sign-in for testing
--------------------------

For end-to-end scenarios where you can't use Google OAuth (no browser or
headless environments), ``auth_testing.md`` at the repo root documents the
"seed a session" pattern:

1. Insert a ``users`` row with a chosen ``user_id`` + ``email``.
2. Insert a ``user_sessions`` row with a chosen ``session_token`` and a far-
   future ``expires_at``.
3. Send subsequent requests with either the ``session_token`` cookie or an
   ``Authorization: Bearer <session_token>`` header.

``memory/test_credentials.md`` (git-ignored) is where actively-used test
credentials should be recorded for the testing agent. Check that file first
before creating new ones.

Testing protocol with the platform agents
-----------------------------------------

The file ``test_result.md`` at the repo root is the **single source of truth**
between the main dev agent and the testing sub-agents. Its top block ("START
- Testing Protocol") is *never* edited; the YAML below it accumulates the
current backlog of ``backend`` / ``frontend`` tasks, their status, and
inter-agent messages. When you delegate testing, update that YAML first. See
its own inline instructions.

Local vs. supervised
--------------------

* **Supervisor-managed** (this environment): ``sudo supervisorctl restart
  backend`` picks up code changes; hot-reload is on.
* **Local**: run ``uvicorn server:app --reload --port 8001`` from
  ``backend/`` **only** for a one-off local check. Never leave a rogue
  ``uvicorn`` running. Supervisor manages the process.
