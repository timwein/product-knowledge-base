# M0 deploy playbook

Step-by-step provisioning for Sentinel M0. Follow once. After M0, the
deploy targets stay live and subsequent milestones push to them.

## 1. Neon (Postgres) — ~5 min

1. Sign up at https://console.neon.tech/signup (GitHub login).
2. Create project: name `sentinel`, Postgres 16, US East (match Railway region below).
3. SQL Editor → run `CREATE EXTENSION IF NOT EXISTS vector;`
4. Paste contents of `sentinel/curator/sentinel_curator/schema.sql` into the SQL Editor → **Run**.
5. **Dashboard → Connection Details → Pooled connection** → copy the `postgres://...` URL.
   Save it; pastes into Railway AND Vercel as `DATABASE_URL`.

## 2. Clerk — ~3 min

1. Sign up at https://dashboard.clerk.com/sign-up.
2. Create application: `Sentinel`. Enable Email + Google.
3. **API Keys** (left sidebar) → copy:
   - `Publishable key` (`pk_test_...`) → Vercel as `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
   - `Secret key` (`sk_test_...`) → Vercel AND Railway as `CLERK_SECRET_KEY`

## 3. Anthropic API key — ~2 min

1. https://console.anthropic.com/settings/keys → **Create key** → label `sentinel-curator`.
2. Copy `sk-ant-api03-...`. Save immediately — only visible once.
3. Used by Railway curator at runtime. Never paste into Claude Code chat
   (Max plan covers chat sessions; this key is for the deployed service).

## 4. Railway (curator) — ~10 min

```sh
brew install railway      # or: npm i -g @railway/cli
cd sentinel/curator
railway login             # browser auth
railway init              # name: sentinel-curator
railway up                # first deploy, ~2-3 min
```

In Railway dashboard for the service:

- **Settings → Networking → Generate Domain.** Copy the URL.
- **Variables** tab → add:

  | Variable               | Value                                        |
  |------------------------|----------------------------------------------|
  | `DATABASE_URL`         | Neon pooled connection                       |
  | `ANTHROPIC_API_KEY`    | `sk-ant-api03-...` from step 3               |
  | `CLERK_SECRET_KEY`     | from step 2                                  |
  | `INTERNAL_HMAC_SECRET` | `openssl rand -hex 32` output                |

  Leave `AGENT_ID`, `AGENT_VERSION`, `ENV_ID`, `STAGING_REPO_URL`,
  `STAGING_REPO_TOKEN` blank — populated in M2.

Verify: `curl https://<railway-domain>/health` → `{"status":"ok",...}`.

## 5. Vercel (web) — ~10 min

```sh
npm i -g vercel
cd sentinel/web
npm install
vercel                    # project name: sentinel, defaults otherwise
```

Vercel dashboard → project → **Settings → Environment Variables** → add
(All Environments):

| Variable                              | Value                              |
|---------------------------------------|------------------------------------|
| `DATABASE_URL`                        | Neon connection (same as Railway)  |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`   | `pk_test_...` from step 2          |
| `CLERK_SECRET_KEY`                    | `sk_test_...` from step 2          |
| `CURATOR_BASE_URL`                    | Railway domain from step 4         |
| `INTERNAL_HMAC_SECRET`                | Same value as Railway              |

Trigger redeploy: `vercel --prod` from `sentinel/web/`.

Verify: `curl https://<vercel-url>/api/health` → ok, visit URL in browser.

## 6. Local development (optional)

```sh
cd sentinel/infra && docker compose up -d           # pg16+pgvector w/ schema
cd ../curator
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env                                # set DATABASE_URL to local
uvicorn sentinel_curator.api:app --reload --port 8000
# curl http://localhost:8000/health

cd ../web
npm install
cp .env.example .env.local                          # set CURATOR_BASE_URL=http://localhost:8000
npm run dev
# open http://localhost:3000 and /api/health
```

## M0 completion gates

- `https://<railway-curator>/health` → 200 ok
- `https://<vercel-web>/api/health` → 200 ok
- Visiting the Vercel URL shows the Sentinel landing page

Send the Railway URL when live and I can verify the health checks from a
Claude Code session.
