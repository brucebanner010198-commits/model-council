# Docs deployment

The user documentation is built from ``docs/source/`` with Sphinx (Furo theme). It's designed to be deployed automatically. Pick either provider below.

## GitHub Pages (recommended, wired up already)

A workflow lives at ``.github/workflows/docs.yml``. On every push:

1. It builds the docs on ``ubuntu-latest`` (Python 3.12).
2. Uploads the ``docs/build/html`` folder as a Pages artifact.
3. **Deploys only from ``main``** (pushes to ``dev`` just verify the build).

### One-time setup

1. Push this repo to GitHub.
2. In the repo: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. Push (or merge) to ``main``. The workflow will run and publish to
   ``https://<user>.github.io/<repo>/``.

The workflow's `deploy` job only runs on `main`, so:

* PRs and pushes to `dev` → build succeeds/fails, no deploy.
* Merge to `main` → build succeeds → publish to Pages.

### Local build

```bash
cd docs
pip install -r requirements.txt
make html
# open build/html/index.html
```

For live-reload while writing:

```bash
pip install sphinx-autobuild
make livehtml
```

## Netlify (alternative)

If you prefer Netlify, ``docs/netlify.toml`` is included. In Netlify's UI:

1. **Add new site → Import from Git → pick this repo**.
2. Set **Base directory** to ``docs``. Netlify reads the rest from
   ``netlify.toml``:

   ```toml
   [build]
     command = "pip install -r requirements.txt && sphinx-build -b html source build/html"
     publish = "docs/build/html"
   ```

3. Netlify will rebuild on every push and give you a
   ``<sitename>.netlify.app`` URL (attach a custom domain from **Domain settings**).

## Vercel (alternative)

Set **Root directory** to ``docs`` and add these settings:

* Build command: ``pip install -r requirements.txt && sphinx-build -b html source build/html``
* Output directory: ``build/html``
* Install command: ``pip --version`` (Vercel needs *some* install command; pip's already on the Python image).

## Custom domain

Both Pages and Netlify support custom domains. Add a ``CNAME`` record pointing at either ``<user>.github.io`` or ``<sitename>.netlify.app``, then declare it in the provider's UI.
