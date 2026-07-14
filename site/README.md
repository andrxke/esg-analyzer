# ESG Report Check — static site

Next.js (App Router, static export) that renders verdict pages from the JSON store
produced by the Python analyzer. Browsing hits the CDN — never the LLM, never a live DB.

## The two steps

```
1. python3 build_data.py     # analyzer → data/ (the one step that calls the LLM)
2. npm run build             # data/ → out/ (static pages)
```

`data/` is **committed** — it's the build input Vercel serves. Vercel only runs step 2.

## Local dev

```bash
pip install pypdf openai          # analyzer deps (repo root: requirements.txt)
export OPENROUTER_API_KEY=sk-or-...
npm run data                      # populate data/ (incremental: unchanged reports skip the LLM)

npm install
npm run dev                       # http://localhost:3000
# or a production check:
npm run build && npm run serve    # serves out/ statically
```

## Adding a company

1. Add an entry to `companies.json` (slug, company, source path, provenance).
2. `npm run data` — only the new report is analyzed (hash-based incremental batch).
3. Commit `companies.json` + the new files under `data/`.
4. Push → Vercel rebuilds.

## Config (env vars, optional)

- `NEXT_PUBLIC_NEWSLETTER_ACTION` — email list form endpoint (Buttondown/Formspree).
- `NEXT_PUBLIC_NEWSLETTER_FIELD` — email field name (default `email`).
- `NEXT_PUBLIC_REQUEST_FORM_URL` — Tally/Google Form URL for company requests.

Unset values degrade gracefully (mailto fallback / disabled note) — no dead links.

## Deploy (Vercel)

Set the project **Root Directory = `site/`** in the Vercel dashboard. Framework
auto-detects as Next.js; `output: 'export'` emits `out/`. No runtime secrets — the
LLM key stays local to `build_data.py`. Deploy-on-push to `main`.
