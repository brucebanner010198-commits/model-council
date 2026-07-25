Data Model
==========

The Council uses **MongoDB** through the async ``motor`` driver. There are
**five collections**. All IDs are UUID-v4 strings (never Mongo
``ObjectId`` — see the "Rules of the road" note in :doc:`configuration`).

Overview
--------

.. list-table::
   :header-rows: 1
   :widths: 20 25 55

   * - Collection
     - Primary lookup
     - Purpose
   * - ``users``
     - ``user_id`` (also unique on ``email``)
     - Account record.
   * - ``user_sessions``
     - ``session_token``
     - Long-lived (7-day) browser sessions.
   * - ``magic_links``
     - ``token_hash``
     - Single-use email sign-in tokens (SHA-256 hashed).
   * - ``settings``
     - ``_id == user_id``
     - Per-user API keys, routing, model overrides, personas.
   * - ``sessions``
     - ``id`` (UUID), scoped by ``owner == user_id``
     - Council conversations: turns, notes, review, verdict, synthesis.

``users``
---------

.. code-block:: json

   {
     "user_id":   "user_a1b2c3d4e5f6",
     "email":     "jane@example.com",
     "name":      "Jane Doe",
     "picture":   "https://…/avatar.png",
     "created_at":"2026-07-14T09:12:33+00:00"
   }

* ``email`` is unique — both auth flows merge into a single record by email.
* ``user_id`` is minted server-side (``user_<12hex>``) and is the canonical
  ownership key everywhere else.

``user_sessions``
-----------------

.. code-block:: json

   {
     "user_id":       "user_a1b2c3d4e5f6",
     "session_token": "8bJZ…_urlsafe32bytes…",
     "expires_at":    "2026-07-21T09:12:33+00:00",
     "created_at":    "2026-07-14T09:12:33+00:00"
   }

* ``session_token`` is a 32-byte ``secrets.token_urlsafe`` value stored in
  clear (it doubles as the browser cookie value). Compromising the DB
  would compromise active sessions — protect the DB accordingly.
* On logout, the row is deleted. Expired rows are rejected at read time
  (a periodic sweep is a good future addition but not required for
  correctness).

``magic_links``
---------------

.. code-block:: json

   {
     "email":      "jane@example.com",
     "token_hash": "3f0a…sha256hex…",
     "used":       false,
     "expires_at": "2026-07-14T09:27:33+00:00",
     "created_at": "2026-07-14T09:12:33+00:00"
   }

* Only the **hash** is stored — see :doc:`authentication`.
* Verified tokens flip ``used=true`` atomically before user lookup, so a
  replayed link fails with 400.

``settings``
------------

The document ``_id`` **is** the user's ``user_id``.

.. code-block:: json

   {
     "_id": "user_a1b2c3d4e5f6",

     "openrouter_key":  "sk-or-…",
     "provider_keys":   { "openai": "sk-…", "anthropic": "…" },

     "models":          { "gpt": "openai/gpt-5.6" },
     "native_models":   { "gpt": "gpt-5.6" },
     "routing":         { "gpt": "auto",  "kimi": "openrouter" },
     "personas":        { "claude": "a fierce open-source advocate" },
     "notetaker_model": "gpt-4o-mini"
   }

Notes
~~~~~

* All fields are **optional**. A missing sub-field falls back to the
  defaults in ``COUNCIL`` / ``NOTETAKER`` / env vars.
* API responses **never** echo any key value; they return booleans in
  ``providers_configured`` and ``openrouter_configured`` instead.
* Per-user keys **override** the server-level env keys (``OPENAI_API_KEY``,
  ``OPENROUTER_API_KEY``, etc.).

``sessions``
------------

Everything about a single council discussion is denormalised into one
document.

.. code-block:: json

   {
     "id":              "b3e0…",
     "owner":           "user_a1b2c3d4e5f6",
     "title":           "Should we bet the company on agents?",
     "participant_ids": ["gpt", "claude", "gemini", "deepseek", "kimi"],
     "status":          "active",
     "created_at":      "2026-07-14T09:12:33+00:00",

     "turns": [
       {
         "id":            "…uuid…",
         "speaker_id":    "human",         // or a member id, e.g. "gpt"
         "speaker_name":  "You",
         "color":         "#ffffff",
         "text":          "…",
         "ts":            "2026-07-14T09:13:00+00:00"
       }
     ],

     "notes": [
       {"id": "…", "text": "Key point…", "ts": "…"}
     ],

     "review": {
       "generated_at": "…",
       "standings": [
         {"member_id":"gpt","name":"GPT-5.6","color":"#10B981",
          "stance":"…","raw_score":8,"score":100,"votes":2}
       ],
       "mvp_id":   "gpt",
       "mvp_name": "GPT-5.6"
     },

     "conclusion": {
       "text":         "…final verdict…",
       "drafter_id":   "claude",
       "drafter_name": "Claude Opus 5",
       "ts":           "…"
     },

     "synthesis": {
       "question":       "…",
       "text":           "…merged answer…",
       "chairman_id":    "gemini",
       "chairman_name":  "Gemini 3.1 Pro",
       "chairman_color": "#8B5CF6",
       "ts":             "…"
     }
   }

Query patterns
~~~~~~~~~~~~~~

* **List sessions for a user** (dashboard):
  ``db.sessions.find({"owner": uid}).sort("created_at", -1)`` with
  ``turn_count`` computed in Python.
* **Add a turn**: ``$push`` onto ``turns``. No document rewrite needed.
* **Overwrite notes**: ``$set: {"notes": [...]}`` — the Scribe regenerates
  the whole list each time.
* **Blind peer review**: reads only ``turns`` (latest per speaker) and
  writes ``review`` in one ``$set``.
* **Synthesize**: writes new turns *and* ``synthesis`` (+ ``review``) in a
  single update using ``$push.turns.$each`` + ``$set``.

Indexes to add for production
-----------------------------

The MVP relies on Mongo's default ``_id`` index and small collection sizes.
When you deploy at scale, add:

.. code-block:: text

   users.createIndex({email: 1}, {unique: true})
   user_sessions.createIndex({session_token: 1}, {unique: true})
   user_sessions.createIndex({expires_at: 1})            // TTL sweep
   magic_links.createIndex({token_hash: 1}, {unique: true})
   magic_links.createIndex({expires_at: 1}, {expireAfterSeconds: 0})
   sessions.createIndex({owner: 1, created_at: -1})
