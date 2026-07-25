Frontend Walkthrough
====================

The frontend is a **React 19** single-page app scaffolded with Create React
App + CRACO (see ``frontend/craco.config.js``), styled with Tailwind CSS and
shadcn/ui, and driven by React Router.

.. code-block:: text

   frontend/src/
   ├── App.js                     # <BrowserRouter> + <AuthProvider>, routes & Protected
   ├── index.js / index.css / App.css
   ├── contexts/
   │   └── AuthContext.jsx        # user/session state, login, logout, magic bootstrap
   ├── lib/
   │   ├── api.js                 # axios client with 401 interceptor
   │   └── utils.js               # cn(), small helpers
   ├── pages/
   │   ├── Login.jsx              # Google + magic-link sign-in
   │   ├── Home.jsx               # Dashboard: convene, archive, settings
   │   └── Room.jsx               # The council chamber (tiles, controls, transcript)
   └── components/
       ├── VideoTile.jsx          # Per-model tile with active-speaker glow
       ├── Waveform.jsx           # Live audio-reactive waveform
       ├── SettingsDialog.jsx     # Keys, routing, personas, notetaker model
       └── ui/                    # shadcn/ui primitives (button, dialog, ...)

Routing & auth
--------------

``App.js`` mounts three routes:

* ``/login``. The sign-in page (Google button + email input).
* ``/``. Dashboard (``Home``), wrapped in ``<Protected>``.
* ``/session/:id``. The council chamber (``Room``), wrapped in ``<Protected>``.

``<Protected>`` reads ``user`` and ``loading`` from ``useAuth()``. While
``loading`` is true it shows a spinner; if there's no user after loading, it
redirects to ``/login``.

``AuthContext.jsx`` does three things on mount:

1. Checks the URL hash for ``#magic=…``. If present, POSTs
   ``/api/auth/magic/verify`` and stores the returned bearer token.
2. Checks the URL query for ``?session_id=…`` (Emergent OAuth redirect). If
   present, POSTs ``/api/auth/session``.
3. Otherwise calls ``GET /api/auth/me`` to hydrate an existing session.

The API client
--------------

``lib/api.js`` is a small axios wrapper:

* ``baseURL`` = ``process.env.REACT_APP_BACKEND_URL`` (**never** hardcoded).
* ``withCredentials: true`` so the session cookie rides along.
* A response interceptor that, on ``401``, clears any local bearer token and
  bounces the user to ``/login``.
* An ``Authorization: Bearer <token>`` header is set when the magic-link flow
  returned a token (used as a fallback where 3rd-party cookies are blocked).

Every API call in the app goes through this client. Do the same for any new
call so 401s route consistently.

The chamber (``Room.jsx``)
--------------------------

The heart of the app. Loads ``/api/sessions/{id}`` once, then drives the UI:

* **Tiles** (``VideoTile``). One per participant, plus a "You" tile. The
  currently speaking tile gets a coloured glow and shows a ``Waveform`` fed
  by ``AudioContext`` + ``AnalyserNode`` while its audio blob plays.
* **Transcript panel**. Turns rendered in order with per-speaker colour;
  hover a line to replay it via ``/api/tts``.
* **Scribe's notes panel**. Refreshed by ``POST /api/sessions/{id}/notes``.
* **Control dock**:

  - **Mic** → uses ``MediaRecorder`` (webm/opus), streams to ``/api/stt``,
    and drops the transcript into the input.
  - **Address council** → adds a human turn (``/message``), then loops
    through participants calling ``/respond`` for each.
  - **Open the floor / Round table** → same but without a leading human turn.
  - **Auto-debate** → runs N rounds; interruptible via a stop flag.
  - **Peer review** → ``/review`` and renders the standings.
  - **Notes** → refreshes the Scribe.
  - **Conclude** → ``/conclude`` with a chosen drafter.
  - **Export PDF** → hits ``/export`` and downloads the blob.

Audio playback is serialised through a small queue so only one member speaks
at a time. Muting via *voices on/off* toggles a ``voicesOn`` state that
skips the ``<audio>`` playback (but leaves the transcript updating).

Settings dialog
---------------

``SettingsDialog.jsx`` reads ``/api/settings`` on open, lets the user edit:

* OpenRouter key (fallback).
* Per-provider keys (OpenAI, Anthropic, Google, DeepSeek, Moonshot).
* Per-member routing (``auto`` / ``direct`` / ``openrouter``).
* Per-member subscription model name and OpenRouter model ID.
* Per-member persona.
* Notetaker model.

Saves via ``POST /api/settings``. The API **never returns the key values**,
only booleans indicating whether each is configured.

Design system
-------------

* **Tailwind** 3.4 with the standard CRACO preset. Design tokens live in
  ``tailwind.config.js``.
* **shadcn/ui** primitives (Radix UI under the hood) live in
  ``src/components/ui/``. Treat them as internal, copy-in components you
  can modify.
* **framer-motion** for tile / transcript transitions.
* **sonner** for toast notifications.
* **lucide-react** for icons.

Adding a new page
-----------------

1. Create ``src/pages/NewPage.jsx``.
2. Import + add a ``<Route>`` in ``App.js``, wrapping with ``<Protected>``
   unless it's publicly accessible.
3. Use ``api`` from ``lib/api.js`` for all HTTP calls. Don't ``fetch``.
4. Compose UI from ``components/ui/*`` and match the dark ``bg-[#050505]``
   palette used everywhere else.
