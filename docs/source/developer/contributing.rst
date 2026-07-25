Contributing
============

Thanks for extending The Council. This page captures the conventions and
guardrails that keep the codebase small and predictable.

Ground rules
------------

* **Never modify** the protected env variables (``MONGO_URL``, ``DB_NAME`` in
  ``backend/.env``; ``REACT_APP_BACKEND_URL`` in ``frontend/.env``). See
  :doc:`configuration`.
* **Never hardcode** URLs, ports or secrets. Environment variables only.
* All backend routes must be registered on ``api_router`` (prefix ``/api``).
  Anything else won't be reachable from the browser through ingress.
* All frontend HTTP calls must go through ``lib/api.js`` so the 401
  interceptor and cookie/bearer credentials behave consistently.
* Use **UUID-v4** strings for every ID field written to Mongo. Never rely
  on ``ObjectId`` (it isn't JSON-serialisable and makes the API messier).
* Store secrets as **hashes** where you can (see ``magic_links.token_hash``).

Style
-----

* **Python**: 4-space indent, ``black`` compatible (line length ~100).
  Prefer ``async``/``await``; avoid blocking I/O. Type-hint public helpers.
* **JavaScript / JSX**: ESLint config in the repo (``.eslintrc`` via CRA +
  plugins in ``package.json``). Prefer function components + hooks. Keep
  Tailwind class strings readable. Use ``cn()`` from ``lib/utils.js`` when
  composing conditionally.
* **Docs**: reStructuredText for developer/user pages; use plain English
  sentences, not marketing copy.

Adding backend functionality
----------------------------

Checklist for a new endpoint (see :doc:`backend` for details):

1. Define request/response Pydantic models with ``max_length`` on free text.
2. Register the route on ``api_router``.
3. Depend on ``get_current_user`` (unless it's genuinely public).
4. Depend on ``rate_limit`` for anything that hits an LLM or file upload.
5. Scope all Mongo reads/writes on ``owner == user.user_id``.
6. Route LLM calls through ``generate()``. Do not call providers directly.
7. Add / update tests in ``backend/tests/`` for happy path + auth boundary.
8. If the response shape changed, update :doc:`api-reference`.

Adding frontend functionality
-----------------------------

1. Use ``api`` from ``lib/api.js`` for every HTTP call.
2. Compose UI from ``components/ui/*`` (shadcn/ui) and keep the dark
   ``bg-[#050505]`` palette.
3. Wrap protected routes with ``<Protected>`` in ``App.js``.
4. If a new page loads data, add a loading state and a friendly empty state.
   The Council never shows a blank screen.
5. Announce user-visible errors with a ``sonner`` toast, not with an alert.

Model-routing conventions
-------------------------

* Only member entries in ``COUNCIL`` may add new providers. Adding a
  provider means:
  (a) an entry in ``PROVIDERS`` with a working OpenAI-compatible ``base``,
  (b) a valid ``native_model`` for that provider, and
  (c) a matching OpenRouter model id in ``model`` for fallback.
* Voice mapping: pick from the OpenAI TTS voice set
  (``alloy | echo | fable | onyx | nova | sage | shimmer``). Give the
  member a distinct voice so users can tell speakers apart audibly.
* Never leave a member without a fallback path. If you ship a provider
  the user is unlikely to have a key for, set its default routing to
  ``openrouter``.

Rate limits and abuse
---------------------

Every new expensive endpoint **must** add ``_rl: None = Depends(rate_limit)``.
The default budget is ``RATE_LIMIT=60`` requests/minute/IP. Also:

* Cap upload sizes explicitly (like ``/api/stt``'s 25 MB check).
* Cap Pydantic string fields with ``max_length``. The request will be
  rejected with 422 before it ever hits your code.

Documentation
-------------

Anything user-facing must land in the **User Guide** in
``docs/source/user/``. Anything a maintainer needs to know goes in
``docs/source/developer/``. Cross-link generously with ``:doc:`` /
``:ref:``.

Rebuild locally:

.. code-block:: bash

   cd docs
   pip install -r requirements.txt
   make html

Working with the platform agents
--------------------------------

* **Testing agents** rely on ``test_result.md``. Update the YAML block
  below the protocol header *before* delegating. Never edit the protocol
  header itself.
* **Test credentials** used across runs go in ``memory/test_credentials.md``
  (git-ignored). Keep it current or the testing agent will need to guess.
* **Deployment**. See :doc:`deployment`. The supervisor commands and
  ingress rules described there apply everywhere.

Git hygiene
-----------

* ``.gitignore`` at the repo root already covers ``.env`` files,
  ``__pycache__``, ``node_modules``, build folders, audio artefacts and
  ``memory/test_credentials.md``. Add new build outputs there.
* Prefer small, self-contained commits with a scope prefix
  (``backend:`` / ``frontend:`` / ``docs:``).
* Never commit anything containing a real provider or session secret.

Where to ask
------------

* Broken production sign-in / cookies? Start at :doc:`authentication`.
* Model won't answer? Start at :doc:`architecture` (routing) and the
  ``/api/council`` provider-status flags.
* Docs won't build? Ensure ``docs/requirements.txt`` is installed and
  ``sphinx_design`` is present (used by ``.. grid::`` on the landing page).
