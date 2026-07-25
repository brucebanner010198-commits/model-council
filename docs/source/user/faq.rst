FAQ
===

**Do I need to pay for all five models?**
   No. Any single option (a subscription, one provider key, or an OpenRouter key) is
   enough to start. Add more later to run more members natively.

**Can I use my ChatGPT Plus or Claude Pro subscription?**
   Yes, for personal use. See :ref:`subscription-setup` in :doc:`settings-and-keys`. This
   feature is marked *experimental* because it depends on OAuth flows the providers can
   change at any time. Sharing subscription tokens across users violates provider ToS,
   so this is not suitable for a public multi-user deployment.

**Are my conversations private?**
   Yes. Every user has isolated sessions and settings. Other users cannot see your data,
   and your keys are never returned by the app.

**Why did a model fall back to OpenRouter?**
   Its subscription or API key was missing or errored for that turn, so the app used
   your OpenRouter fallback for that one model. It's per-model and automatic.

**The models won't respond.**
   Make sure you've added at least one option in **Configure**. If you see an "add key"
   notice, that's why.

**Can the models talk to each other on their own?**
   Yes. Use **Auto-debate** to let them argue autonomously for a few rounds, or **Open
   the floor** to have them start the discussion.

**What's the difference between Conclude and Synthesize?**
   *Conclude* drafts a verdict from an ongoing discussion. *Synthesize* answers a single
   question by fanning it to all models in parallel and merging the best answer. See
   :doc:`synthesize-and-verdicts`.

**How do I get my data out?**
   Use **Export PDF** in any session for a full record. Transcript, notes, standings,
   verdict.

**A magic-link didn't work.**
   Links are single-use and expire in 15 minutes. Request a fresh one.
