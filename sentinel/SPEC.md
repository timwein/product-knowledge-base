# Sentinel — Build Spec (v0.1)

Session handoff doc. All decisions below were made in a prior planning session.

## Source repos (all on GitHub under `timwein/`)

The existing knowledge base is split across three repos. The next session
needs read access to all of them (add to GitHub MCP scope):

- **`tweet-knowledge-base`** — the current KB. Contains analyzed posts that
  will be copied verbatim as backfill for new Sentinel users, plus the seed
  corpus of blogs.
- **`blog-ingestion-agent`** — the curator we are reusing. Contains the
  Managed Agent definition, system prompts (especially the
  structured-analysis prompt), tools, and any scoring/discovery logic.
- **`saved-tweet-ingestion-agent`** — sibling agent for tweets. Not used by
  Sentinel v1 (blogs only), but read it for context if anything in
  `blog-ingestion-agent` references shared patterns.

**Sentinel itself is built in `product-knowledge-base`** (this repo) on
branch `claude/verify-claude-max-usage-OvBIf`.

## Component inventory

Components that make up the existing KB project, and where each one lives.
Sentinel v1 only uses a subset (see "Scope" note below).

| # | Component | Repo | Key files |
|---|---|---|---|
| 1 | Bookmarker agent (fetches X bookmarks) | `saved-tweet-ingestion-agent` | `run_bookmarker.py`, `lib/bookmarker.py`, `lib/bookmark_prompts.py`, `setup_bookmarker.py`, `com.timwein.tweet-bookmarker.plist` |
| 2 | Tweet ingestion agent | `saved-tweet-ingestion-agent` | `run.py`, `setup.py`, `lib/prompts.py`, `lib/fetcher.py`, `lib/feed_fetcher.py` |
| 3 | Blog ingestion agent | `blog-ingestion-agent` | `run.py`, `setup.py`, `blog-ingest.yml`, `kb-blog-curator.system.md` |
| 4 | Podcast ingestion agent | `blog-ingestion-agent` | `podcast-run.py`, `podcast-setup.py`, `podcast-ingest.yml`, `kb-podcast-curator.system.md` |
| 5 | Vercel reader app (Next.js) | `tweet-knowledge-base` | `reader/app/**`, `reader/components/**`, `reader/app/api/{analyze,chat,rate,reads,revalidate}/route.ts` |
| 6 | Structured analysis prompts | split across ingestion repos | Tweet bookmark: `saved-tweet-ingestion-agent/lib/bookmark_prompts.py` • Tweet ingest: `saved-tweet-ingestion-agent/lib/prompts.py` • Blog: `blog-ingestion-agent/kb-blog-curator.system.md` • Podcast: `blog-ingestion-agent/kb-podcast-curator.system.md` |

### Scope: what Sentinel v1 uses vs. defers

- **Use in v1:** #3 (blog ingestion agent), #6 (blog prompt only), and #5
  (reader app) — Sentinel's web app should start by reading the existing
  Next.js reader in `tweet-knowledge-base/reader/` and deciding whether to
  fork/extend it in-place, port it into `sentinel/web/`, or rebuild. The
  existing reader has API routes (`analyze`, `chat`, `rate`, `reads`,
  `revalidate`) that likely cover features we'd otherwise reinvent.
- **Defer to v2:** #1 tweet bookmarker, #2 tweet ingestion, #4 podcast
  ingestion. Sentinel v1 is blogs-only by prior decision. But the
  multi-source architecture should leave room for these to plug in later
  — `sources.kind` already allows non-blog values in the data model.

### Open question raised by this inventory

The decision to "build Sentinel's web app in `sentinel/web/`" assumed there
was no existing reader. There is. **Before scaffolding the Next.js app,
the next session should read `tweet-knowledge-base/reader/` and propose
one of:**
  - **A.** Fork the existing reader into `sentinel/web/` and adapt it for
    multi-tenant + Clerk + the new data model. Probably fastest.
  - **B.** Productionize the reader in place inside `tweet-knowledge-base`
    and make `product-knowledge-base` the home only for new services
    (Python curator, infra, migrations). Cleaner separation but more repos
    to coordinate.
  - **C.** Rebuild from scratch in `sentinel/web/` because the existing
    reader is too coupled to the single-user/tweet model to retrofit
    cleanly. Slowest, only if A and B are both bad.

**Resolved (session 2):** none of A/B/C. The existing reader stays
untouched as Tim's personal reader; Sentinel builds a separate
multi-tenant reader from scratch in `sentinel/web/`. See §"Locked
decisions (session 2)".

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
schema**, read the following from the three source repos:

From **`blog-ingestion-agent`**:
1. **Managed Agent definition** — model, tools, system prompt(s), agent config.
2. **Structured-analysis system prompt** — this defines the schema of
   `posts.structured_analysis` in Sentinel's DB.
3. **How the agent is invoked today** — API call shape, auth, expected
   inputs, expected output schema, latency, cost per call.
4. **Discovery / scoring logic** — anything outside the agent itself that
   contributes to ranking or new-source suggestions.

From **`tweet-knowledge-base`**:
5. **Sample structured-analysis outputs** — 2–3 real post analyses, to
   confirm the actual shape (prompts and outputs sometimes drift).
6. **Existing seed corpus** — the list of blogs + topics + any
   per-source metadata, to port into `sentinel/seed-corpora/ai.yaml`.
7. **Existing KB data** — the analyzed posts that get copied verbatim
   as backfill for new users. Need to know:
   - storage format (JSONL? Postgres dump? files in the repo?)
   - how many posts exist
   - whether posts include extracted full text or only analysis

From **`saved-tweet-ingestion-agent`** (context only):
8. Skim to see if it shares any infrastructure with `blog-ingestion-agent`
   that Sentinel should also reuse. Not load-bearing for v1.

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

## Locked decisions (session 2)

Decisions made in the read-the-source-repos session after the three source
repos (`blog-ingestion-agent`, `tweet-knowledge-base`,
`saved-tweet-ingestion-agent`) were read in full. These resolve the open
questions raised in the v0.1 spec.

### Multi-tenancy

**Single global Managed Agent + per-user inputs.** Keep one `agent_id`.
Genericize the existing `kb-blog-curator.system.md` system prompt: replace
hard-coded "Tim Weingarten" / interest-list strings with a
`<user_display_name>` and `<user_interests>` block injected at session
kickoff. Pass per-user seed files (subscriptions, pinned sources, recent
signals) at session creation via the Files API and `resources` param. Do
not fork the agent per signup.

Schema impact:

- `tim_score` is removed from the `posts.structured_analysis` YAML and
  becomes `user_post_scores.score` (the per-user join table already in
  the data model). The agent emits `relevance_score` only; user ratings
  live per-user.
- The agent's profile state — `deltas.md`, `evolution.md`, `feedback.md`,
  `discovered_sources.md`, `pinned_sources.md`, `feed_map.json` — becomes
  per-user. See "Storage transport" below for how it materializes.

### Reader app

**Leave `tweet-knowledge-base/reader/` untouched.** It stays Tim's
personal reader against his existing single-user KB. Build the Sentinel
multi-tenant reader from scratch in `sentinel/web/` in this repo
(`product-knowledge-base`). The existing reader can be read for
inspiration — do not import its code unless a specific component
(rendering an analysis Markdown file, the rating UI, etc.) pays off and
is cleanly extractable.

### Backfill

**Port all 468 existing blog analyses verbatim** as backfill for new
Sentinel users at signup. Same scores, same blurbs, same structured
analyses for everyone on day one. New posts ingested after signup are
scored per-user.

**Filter rule.** Drop any analysis that touches Tim's personal financial
exposure: his Anthropic equity, his stake or portfolio, Anthropic's
valuation discussed in a personal-investment context. Analyses of
Anthropic's public strategy, research, platform, or model releases stay
— that's public commentary and is the seed corpus's value.

**Process.** Before backfill ships, scan all 468 `blog-*.md` files in
`tweet-knowledge-base/2026/**/` for personal-finance mentions and surface
a candidate-drop list to Tim for eyeball review. No silent heuristic
filter — Tim reviews and approves the drop list.

### Storage transport (agent → DB)

**Shared staging git repo + sync worker.** The Managed Agent commits
analyses to a Sentinel-controlled staging git repo (user_id embedded in
path prefix, e.g. `users/<user_id>/2026/MM/DD/blog-*.md`), using the same
incremental-commit pattern the existing system prompt already encodes —
one analysis = one commit+push. A Python sync worker on the Sentinel
curator service watches the staging repo, parses Markdown + YAML for new
commits, and upserts into Postgres (`posts`, `user_post_scores`).

The per-user profile state (deltas, evolution, discovered_sources,
feedback, feed_map, pinned_sources) also lives in this staging repo
namespaced per user. The sync worker mirrors it into the corresponding
per-user Postgres rows (or back into the repo when the agent needs to
read it — TBD which direction is canonical, decide during M2).

This minimizes the rewrite to the existing system prompt: file paths
change (add user_id prefix), the remote URL changes, but the file-
discipline / incremental-commit / dedupe-log machinery is preserved.

### Resolved open questions

- §50 (reader app A/B/C) — neither; option D above.
- §247 multi-tenancy — single global agent + per-user inputs.
- §247 KB backfill verbatim acceptable — yes, with the personal-finance
  filter above.

Still open (Tim to answer directly in the SPEC):

- Domain / brand: "Sentinel" final?
- Anthropic API key: use Tim's existing one or provision a new one
  scoped to Sentinel for cost attribution?

## Branch

All Sentinel development is on branch `claude/verify-claude-max-usage-OvBIf`
in `timwein/product-knowledge-base`.
