Deployment
==========

The Council is built as a **cross-platform web app** — a React SPA on
``:3000`` and a FastAPI backend on ``:8001``, both hosted behind a
Kubernetes ingress that routes ``/api/*`` to the backend and everything
else to the frontend.

Runtime services
----------------

Inside the environment everything runs under **supervisor**:

.. code-block:: text

   supervisorctl status

   backend            RUNNING   uvicorn server:app --host 0.0.0.0 --port 8001 --reload
   frontend           RUNNING   yarn start   (HOST=0.0.0.0 PORT=3000)
   mongodb            RUNNING   /usr/bin/mongod --bind_ip_all

.. important::

   Never launch ``uvicorn`` or ``yarn`` yourself — they'd conflict with the
   supervisor-managed processes. Use supervisor commands only.

Common commands
~~~~~~~~~~~~~~~

.. code-block:: bash

   sudo supervisorctl status
   sudo supervisorctl restart backend
   sudo supervisorctl restart frontend
   sudo supervisorctl restart all

   tail -n 200 /var/log/supervisor/backend.err.log
   tail -n 200 /var/log/supervisor/frontend.err.log

Environment variables
---------------------

Two ``.env`` files drive everything (see :doc:`configuration`). Anything
holding a secret must live here — **never** hardcode URLs, ports or keys.

* ``backend/.env`` — ``MONGO_URL``, ``DB_NAME``, ``EMERGENT_LLM_KEY``,
  provider fallbacks, ``RESEND_API_KEY``, ``SENDER_EMAIL``, ``RATE_LIMIT``,
  ``APP_BASE_URL``, ``CORS_ORIGINS``.
* ``frontend/.env`` — ``REACT_APP_BACKEND_URL`` only.

After editing a ``.env``:

.. code-block:: bash

   sudo supervisorctl restart backend    # or frontend
   # (dep changes → install first, then restart)

CORS
----

CORS is intentionally permissive with credentials:

.. code-block:: python

   app.add_middleware(
       CORSMiddleware,
       allow_credentials=True,
       allow_origin_regex=".*",       # echoes the request Origin
       allow_methods=["*"],
       allow_headers=["*"],
   )

This lets the app work across preview subdomains and custom domains. For
your production deployment you may prefer to tighten ``allow_origin_regex``
to your own domain(s).

Ingress and URLs
----------------

Kubernetes ingress routes:

* ``/api/*`` → backend on ``:8001``
* everything else → frontend on ``:3000``

Consequences:

* Every backend route **must** live on the ``/api`` prefix (see
  ``server.py`` — routes are registered on ``api_router = APIRouter(prefix="/api")``).
* The frontend **must** call ``${REACT_APP_BACKEND_URL}/api/...``. If you
  drop the ``/api`` prefix, ingress will send the request to the frontend
  and you'll see the SPA HTML instead of JSON.

Provider keys
-------------

The Council is designed to run on **the user's own** provider accounts:

* Voice uses ``EMERGENT_LLM_KEY`` (server-level, required).
* Everything else prefers **per-user keys** from the ``settings`` collection
  and only falls back to server env variables if a user hasn't set their
  own. That keeps costs attributed to the right account.

For a public deployment, the env-level provider keys can stay empty — users
add their own in the Settings dialog. Only ``EMERGENT_LLM_KEY`` is needed
server-side for voice to work out of the box.

Email delivery
--------------

Magic-link sign-in requires ``RESEND_API_KEY``. Without it,
``/api/auth/magic/request`` returns **503** and only Google sign-in works.

* ``SENDER_EMAIL`` defaults to ``onboarding@resend.dev`` (Resend's shared
  sandbox). For production, verify your own domain in Resend and set
  ``SENDER_EMAIL`` to a sender on that domain.
* Resend's sandbox will only deliver to the account owner's verified
  address, so end-to-end magic-link testing needs a verified sender.

MongoDB
-------

* Local dev / this environment: single-node ``mongod`` under supervisor.
* Production: use a managed cluster (Atlas, DocumentDB) and set
  ``MONGO_URL`` to that connection string.

Indexes are not created automatically. See :doc:`data-model` for the set to
add on your production cluster before you take real traffic.

Frontend build
--------------

For a real production deployment (rather than the CRA dev server on
``:3000``):

.. code-block:: bash

   cd frontend
   yarn install --frozen-lockfile
   yarn build

That produces ``frontend/build/`` — a static bundle you can serve from any
CDN or reverse-proxy. Point your public routing rules so ``/api/*`` still
hits the backend and everything else serves ``index.html``.

Building the docs
-----------------

.. code-block:: bash

   cd docs
   pip install -r requirements.txt
   make html
   # open build/html/index.html

For live-reloading while writing docs:

.. code-block:: bash

   pip install sphinx-autobuild
   make livehtml

Deploying the docs
~~~~~~~~~~~~~~~~~~

Two options ship out of the box (full walkthrough in ``docs/DEPLOY.md``):

* **GitHub Pages** — a workflow at ``.github/workflows/docs.yml`` builds the docs on every push and deploys to Pages on ``main``. One-time setup: enable **Settings → Pages → Source: GitHub Actions** in the repo.
* **Netlify** — ``docs/netlify.toml`` is included. In Netlify: *Add new site → Import from Git → Base directory: docs*. Netlify reads the rest.

The built ``docs/build/html/`` is a static site, so anywhere that serves static HTML also works (Vercel, S3+CloudFront, or alongside the frontend build under ``/docs/``).

Health checklist
----------------

Before you consider a deploy done, verify:

* ``GET /api/`` → ``{"message": "AI Model Council API"}`` (200).
* ``GET /api/auth/me`` unauthenticated → ``401``.
* Google sign-in returns to the app and shows the dashboard.
* Magic-link sign-in delivers an email that signs you in on click.
* Adding a provider key in Settings enables that member (``providers[i].configured = true``
  in ``/api/council``).
* A short round-table produces spoken audio for every seated member.
* ``Export PDF`` downloads a non-empty file with the transcript.
