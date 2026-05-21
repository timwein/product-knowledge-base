# Sentinel — Build Spec (v0.1)

Session handoff doc. All decisions below were made in a prior planning session.
The other session has access to the source repos for Tim's existing blog
knowledge base (managed agent + system prompts + seed corpus + KB data).

## Product summary

Sentinel is a personal blog knowledge base. A user signs up, picks
prepackaged seed corpora and/or pastes their own interests, and a background
curator continuously discovers and ranks blog posts for them. Reader UI is
focused; reading behavior feeds back into ranking.

The curator is **not new code** — it is Tim's existing blog-ingestion agent
running on Claude Managed Agents, with its existing structured-analysis
system prompt. Sentinel's Python service is a thin wrapper that invokes that
agent per-user with the right inputs.

## Locked decisions

### Product
- **Sources:** blogs only for v1 (no Twitter, newsletters, podcasts).
- **Onboarding:** Clerk signup → pick prepackaged seed corpora → optional
  custom seeds (paste blog URL, autodiscover RSS) → first curation runs
  synchronously so user lands on a populated reader.
- **Seed corpora at launch:** port Tim's existing AI-focused seed corpus
  verbatim from the existing KB repo. No other corpora in v1.
- **Custom source addition:** paste a blog homepage URL; Sentinel
  autodiscovers RSS via `<link>` tags and common feed paths.
- **Access:** open signup.

### Feed & reader
- **Feed ordering:** score-ranked, newest-first within score band.
- **Reader view:** shows the same structured analysis that Tim's existing
  KB generates. Schema in Sentinel's DB must mirror the structured-analysis
  prompt's output shape exactly.
- **Per-post actions:** thumbs up / thumbs down / save / archive /
  "more like this" / "less like this source".

### Curation
- **Curator agent:** Tim's existing blog-ingestion agent on Claude Managed
  Agents. Reused verbatim — same model, same tools, same scoring rubric,
  same structured-analysis system prompt.
- **Triggers:**
  - Cron at 6am and 3pm in each user's local timezone.
  - Manual "Refresh" button in the UI.
- **Discovery of new sources:** auto-add high-confidence discoveries
  (heavily linked from existing high-score posts AND topically aligned),
  surface the rest in a "Suggested sources" panel for user approval.
- **Personalization (v1):** recent user signals (thumbs/saves/archives)
  passed into the agent's prompt as context each run. No learned per-user
  taste vector in v1.
- **Backfill on signup:** copy Tim's existing KB's analysis **verbatim** —
  same scores, same blurbs, same structured analysis for every new user on
  day one. New posts ingested after signup get scored per-user.

### Notifications
- **In-app only.** No email digest, no push, no re-engagement nudges in v1.

### Cost guardrails
- **Per-user daily token budget with hard cap.** When exceeded, that user's
  next run is skipped and they see a banner.

### Build sequencing
- Scaffold the whole **M0 in one push**: Next.js shell + Clerk + Python
  service shell + Postgres schema + deploy targets live with health checks.

## Architecture

```
Next.js (Vercel)          Python curator (Railway/Fly)         Postgres (Neon)
- marketing               - FastAPI entrypoint                  - pgvector
- Clerk auth              - apscheduler cron                    - per-user KB
- onboarding wizard       - invokes Managed Agent per user      - signals
- reader UI (RSC)         - RSS fetch + readability             - jobs
- server actions          - shared HMAC for internal calls
```

- Auth between services: shared HMAC secret on internal endpoints; user
  identity passed as Clerk user ID, verified via Clerk JWT when called from
  Next.js.
- Scheduling: `apscheduler` in the Python service picks up users whose
  `next_curate_at` has passed.

## Data model (Postgres)

- `users` — Clerk user id (PK), email, timezone, curation_cadence_hours,
  daily_token_budget, tokens_used_today, tokens_reset_at, created_at.
- `seed_corpora` — id, slug, name, description, curated_at.
- `seed_corpus_sources` — corpus_id → source_id.
- `sources` — id, kind (`blog`), url, feed_url, title, description,
  embedding, last_fetched_at, status.
- `user_sources` — user_id, source_id, origin (`seed`|`custom`|`discovered`),
  state (`active`|`muted`), created_at.
- `user_interests` — user_id, freeform_text, embedding.
- `posts` — id, source_id, url (unique), title, author, published_at,
  fetched_at, full_text, embedding,
  **structured_analysis JSONB** (shape determined by Tim's existing
  structured-analysis prompt — TBD until we read it).
- `user_post_scores` — user_id, post_id, score, agent_blurb, ranked_at.
- `user_signals` — user_id, post_id, kind (`up`|`down`|`save`|`archive`
  |`open`|`dwell_ms`), created_at.
- `jobs` — id, user_id, kind, state, started_at, finished_at, error, payload.

Note: `posts.structured_analysis` schema is the load-bearing unknown.
**Do not finalize migrations until the existing structured-analysis prompt
has been read.**

## Repo layout (planned)

```
sentinel/
  SPEC.md                   # this file
  web/                      # Next.js app
    app/
    components/
    lib/
    drizzle/                # or prisma/
  curator/                  # Python service
    sentinel_curator/
      agent.py              # thin wrapper over Managed Agent
      fetch.py              # RSS + readability
      scoring.py
      discovery.py
      jobs.py
      api.py                # FastAPI
      schema.sql
    pyproject.toml
  seed-corpora/             # YAML/JSON ports of Tim's existing seed
    ai.yaml
  infra/
    docker-compose.yml      # local dev: postgres+pgvector
    railway.toml or fly.toml
```

## Milestones

1. **M0 — scaffold:** Next.js shell, Python service shell, Postgres
   schema, Clerk wired, deploy targets live with health checks. No
   curation yet.
2. **M1 — ingestion:** RSS fetch + full-text extraction + post storage
   for hardcoded sources. Read posts in feed (chronological, unranked).
3. **M2 — wire managed agent:** invoke Tim's existing blog-ingestion
   agent from Python per post; store structured analysis; ranked feed.
4. **M3 — onboarding wizard:** seed corpora + custom seeds + KB backfill
   copy + first-run curation.
5. **M4 — signals + discovery:** thumbs/save/archive feedback into
   agent prompt; auto-add high-confidence sources; suggested-sources panel.
6. **M5 — polish:** search, settings, error states, token budget UI.

## What the next session needs to do first

**Before writing any curator code or finalizing the `posts.structured_analysis`
schema**, read these from the other repos (which the next session has
access to):

1. **Managed Agent definition** for Tim's blog-ingestion agent — model,
   tools, system prompt(s), any agent config.
2. **Structured-analysis system prompt** — this defines the schema of
   `posts.structured_analysis` in Sentinel's DB.
3. **Sample structured-analysis outputs** — 2–3 real post analyses, to
   confirm the actual shape (prompts and outputs sometimes drift).
4. **Existing seed corpus** — the list of blogs + topics + any
   per-source metadata, to port into `sentinel/seed-corpora/ai.yaml`.
5. **Existing KB data** — the analyzed posts that get copied verbatim
   as backfill for new users. Need to know:
   - storage format (JSONL? Postgres dump? S3?)
   - how many posts exist
   - whether posts include extracted full text or only analysis
6. **How the agent is invoked today** — API call shape, auth, expected
   inputs, expected output schema, latency, cost per call.

Once those are read, the next session should:

- Finalize `posts.structured_analysis` JSONB schema in
  `sentinel/curator/sentinel_curator/schema.sql`.
- Confirm whether the Managed Agent assumes a single global KB; if so,
  flag what per-user adaptation is needed and ask Tim before diverging.
- Start M0 scaffolding.

## Open questions for Tim (not yet answered)

- Does the existing blog-ingestion agent assume a single global KB, or
  is it already parameterized by user? (Determines whether Sentinel
  passes user interests/signals into each invocation or has to fork
  the agent for multi-tenant use.)
- KB backfill: copying analysis verbatim means every new user sees the
  same scores. Is that acceptable for the AI-focused seed at launch,
  or do we need per-user rescoring of backfilled posts before M3 ships?
  (Tim said verbatim is fine for now; flagging in case it should be
  revisited after seeing real onboarding feel.)
- Domain / brand: "Sentinel" is the working name. Final?
- Anthropic API key: use Tim's existing one or provision a new one
  scoped to Sentinel for cost attribution?

## Branch

All Sentinel development is on branch `claude/verify-claude-max-usage-OvBIf`
in `timwein/product-knowledge-base`.
