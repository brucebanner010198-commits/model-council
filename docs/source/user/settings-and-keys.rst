Settings & Keys
===============

The Council runs each model on **your own accounts**, so you stay in control of usage and
cost. Open **Configure** (top-right) to manage this. All keys are stored securely and are
**never shown back** to you or anyone else.

Two ways to power the models
----------------------------

**1. Subscription / provider keys (recommended, default)**
   Paste your own API key for any provider — OpenAI, Anthropic, Google Gemini, DeepSeek,
   or Moonshot (Kimi). That model then calls its provider directly.

**2. OpenRouter (fallback)**
   Paste an OpenRouter key. It's used automatically for any model whose subscription key
   is missing or temporarily failing.

.. important::

   "Subscription" here means a provider **API key** (billed to that provider account).
   Consumer plans like ChatGPT Plus, Claude Pro or Gemini Advanced do **not** grant API
   access, so they can't be used to make calls.

Per-model routing
-----------------

For each member you can choose how it's routed:

* **Auto** — try your subscription key first, fall back to OpenRouter on error/missing key.
* **Subscription only** — prefer your provider (still falls back on hard errors).
* **OpenRouter only** — always use OpenRouter.

You can also edit each member's **subscription model name** and **OpenRouter model ID** if
you want to pin a specific model version, and give an optional **persona**.

Voices
------

Voice (models speaking, and transcribing your mic) works out of the box — no key needed.

Fallback is per-model
---------------------

If, say, your DeepSeek key hits a limit, only **DeepSeek** falls back to OpenRouter for
that turn — every other model keeps using your subscription. Nothing else is affected.
