Developer & Maintainer Guide
============================

This guide is for engineers running, extending or maintaining The Council.

At a glance
-----------

* **Frontend:** React 19 SPA (React Router, Tailwind, shadcn/ui, framer-motion), talks to
  the backend exclusively via ``REACT_APP_BACKEND_URL``.
* **Backend:** FastAPI (async) + Motor (MongoDB). All routes are prefixed with ``/api``.
* **Voice:** OpenAI TTS + Whisper via ``emergentintegrations`` (uses ``EMERGENT_LLM_KEY``).
* **Models:** native OpenAI-compatible provider endpoints with per-model OpenRouter fallback.
* **Auth:** Emergent Google login **and** email magic-link (Resend), merged by email;
  cookie/Bearer sessions; per-user data isolation.

Where things live
-----------------

.. code-block:: text

   /app
   ├── backend/
   │   ├── server.py           # entire FastAPI app (routes, auth, routing, voice, PDF)
   │   ├── requirements.txt
   │   ├── .env                # secrets & config (never committed)
   │   └── tests/              # pytest suite (auth, isolation, providers, magic-link)
   ├── frontend/
   │   └── src/
   │       ├── App.js                    # routes + AuthProvider + Protected routes
   │       ├── contexts/AuthContext.jsx  # login/logout, session/magic bootstrap
   │       ├── lib/api.js                # axios client (+ 401 interceptor)
   │       ├── pages/                     # Login, Home, Room
   │       └── components/                # VideoTile, Waveform, SettingsDialog, ui/
   ├── docs/                   # this documentation
   └── memory/                 # PRD.md, test_credentials.md

Read next
---------

* :doc:`architecture`. Request flow and model routing.
* :doc:`configuration`. Environment variables.
* :doc:`backend` / :doc:`frontend`. Code walkthroughs.
* :doc:`api-reference`. Every endpoint.
* :doc:`authentication`. Session + magic-link internals.
* :doc:`data-model`. MongoDB collections.
* :doc:`testing`. How the suite is structured and run.
* :doc:`deployment`. Running under supervisor and going live.
* :doc:`contributing`. Conventions and guardrails.
