# Sentinel

A multi-tenant personal-blog knowledge base. The build spec lives in
[`SPEC.md`](./SPEC.md) — read that first.

## Status

**M0 — scaffold.** Code laid down for Next.js web shell, Python curator
service, Postgres schema with pgvector, local Docker dev environment,
Railway deploy config, and an initial AI seed corpus. No curation logic
yet; that's M2.

## Repo layout

```
sentinel/
  SPEC.md                    # build spec (read first)
  README.md                  # this file
  web/                       # Next.js 16 app (App Router) + Clerk
    app/                     # routes
      page.tsx               # landing
      api/health/route.ts    # health check
    components/              # (empty, fill in M1+)
    lib/                     # (empty, fill in M1+)
    middleware.ts            # Clerk
    package.json
  curator/                   # FastAPI Python service
    sentinel_curator/
      api.py                 # FastAPI app w/ /health
      config.py              # env-var loader
      schema.sql             # canonical Postgres DDL
    Dockerfile
    pyproject.toml
  seed-corpora/
    ai.yaml                  # ~30 publications across canonical topics
  infra/
    docker-compose.yml       # local: Postgres + pgvector with schema preloaded
    railway.toml             # curator deployment
```

## Local development

Boot the database first — schema applies on container init:

```sh
cd sentinel/infra
docker compose up -d
```

Run the curator (in another shell):

```sh
cd sentinel/curator
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # fill in secrets
uvicorn sentinel_curator.api:app --reload --port 8000
# curl http://localhost:8000/health
```

Run the web app:

```sh
cd sentinel/web
npm install
cp .env.example .env.local  # fill in Clerk + DB
npm run dev
# open http://localhost:3000 and http://localhost:3000/api/health
```

## Deploy targets

Sentinel uses three providers. Tim provisions accounts, then sets the
secrets noted below.

### 1. Neon (Postgres)

- Create a Neon project. Enable the `pgvector` extension.
- Run `curator/sentinel_curator/schema.sql` against the database (Neon
  has a SQL editor in the dashboard, or use `psql`).
- Copy the connection string → both Railway and Vercel secret managers
  as `DATABASE_URL`.

### 2. Railway (curator)

```sh
cd sentinel/curator
railway init                       # one-time, link to a new Railway project
railway up                         # deploy
```

Set these in Railway's variables UI:

| Variable                | Value                                      |
|-------------------------|--------------------------------------------|
| `DATABASE_URL`          | Neon connection string                     |
| `ANTHROPIC_API_KEY`     | Sentinel-scoped key (NOT Tim's personal)   |
| `CLERK_SECRET_KEY`      | Clerk Backend API key                      |
| `INTERNAL_HMAC_SECRET`  | random 32+ byte string                     |
| `AGENT_ID`              | populated by `setup.py` once we build it   |
| `AGENT_VERSION`         | ditto                                      |
| `ENV_ID`                | ditto                                      |
| `STAGING_REPO_URL`      | the Sentinel staging KB repo               |
| `STAGING_REPO_TOKEN`    | GitHub PAT with contents:write             |

Health check is wired to `/health`.

### 3. Vercel (web)

```sh
cd sentinel/web
vercel
```

Set the same secrets the `.env.example` lists, plus
`NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`. Point `CURATOR_BASE_URL` at the
Railway deployment.

## Anthropic credentials

Per [`SPEC.md`](./SPEC.md) §"Anthropic credentials":

- **Claude Code chat sessions** that build Sentinel — billed against Tim's
  Max plan. No API key in the Claude Code environment.
- **Sentinel runtime** (Railway curator + `setup.py` on the build
  machine) — uses a fresh `ANTHROPIC_API_KEY` provisioned specifically
  for Sentinel, for cost attribution. Never in chat or commits.

## What's next (M1)

1. Personal-finance scanner over the 468 existing analyses — **done**.
   See `backfill/personal-finance-candidates.md` for the drop list (Tim
   reviews + strikes through any he wants kept).
2. RSS fetch + readability extraction (`curator/sentinel_curator/fetch.py`).
3. Seed-corpus loader: read `seed-corpora/ai.yaml`, upsert into `sources`
   + `seed_corpora` + `seed_corpus_sources`.
4. Backfill parser: turn each cleared `blog-*.md` into rows in `posts` +
   `user_post_scores` (verbatim per user at signup).
5. Minimal feed UI on the web side (chronological, unranked).

M2 — wire up the Managed Agent (genericize Tim's
`kb-blog-curator.system.md` for multi-tenant use, build the staging-git
sync worker). M3 — onboarding wizard with Clerk + seed-corpus picker.
