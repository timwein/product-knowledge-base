-- Sentinel curator — Postgres schema (M0)
--
-- Source of truth for Sentinel's database. The web app reads this DB
-- (via drizzle or raw client — TBD in M1). The curator service writes to
-- it after parsing Markdown analyses out of the shared staging git repo
-- (see SPEC §"Storage transport").
--
-- Conventions:
-- - User IDs are Clerk user IDs (TEXT, not UUID).
-- - Embeddings are vector(1536) by default — fits text-embedding-3-small.
--   Bump and re-index if you switch to a larger embedding model.
-- - `tim_score` from the existing single-user KB is renamed to `user_score`
--   and lives on user_post_scores (per-user), per session-2 decision.

CREATE EXTENSION IF NOT EXISTS vector;

-- ----- users -----------------------------------------------------------

CREATE TABLE users (
  id                       TEXT PRIMARY KEY,                       -- Clerk user ID (e.g. user_xxx)
  email                    TEXT UNIQUE NOT NULL,
  display_name             TEXT,
  timezone                 TEXT NOT NULL DEFAULT 'UTC',
  curation_cadence_hours   INTEGER NOT NULL DEFAULT 12,
  daily_token_budget       BIGINT NOT NULL DEFAULT 1000000,
  tokens_used_today        BIGINT NOT NULL DEFAULT 0,
  tokens_reset_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  next_curate_at           TIMESTAMPTZ,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----- seed corpora ----------------------------------------------------

CREATE TABLE seed_corpora (
  id           SERIAL PRIMARY KEY,
  slug         TEXT UNIQUE NOT NULL,
  name         TEXT NOT NULL,
  description  TEXT,
  curated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----- sources ---------------------------------------------------------

CREATE TABLE sources (
  id              SERIAL PRIMARY KEY,
  kind            TEXT NOT NULL DEFAULT 'blog' CHECK (kind IN ('blog')),  -- v1 = blog only; expand later
  url             TEXT UNIQUE NOT NULL,
  feed_url        TEXT,
  title           TEXT,
  description     TEXT,
  embedding       vector(1536),
  last_fetched_at TIMESTAMPTZ,
  status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','broken','dropped')),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE seed_corpus_sources (
  corpus_id INTEGER NOT NULL REFERENCES seed_corpora(id) ON DELETE CASCADE,
  source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  PRIMARY KEY (corpus_id, source_id)
);

CREATE TABLE user_sources (
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  origin     TEXT NOT NULL CHECK (origin IN ('seed','custom','discovered')),
  state      TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active','muted')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, source_id)
);

CREATE INDEX user_sources_user_state_idx ON user_sources (user_id, state);

-- ----- user interests --------------------------------------------------

CREATE TABLE user_interests (
  user_id       TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  freeform_text TEXT NOT NULL DEFAULT '',
  embedding     vector(1536),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----- posts -----------------------------------------------------------
-- One row per unique URL. Shared across users. Per-user ranking lives on
-- user_post_scores.
--
-- structured_analysis JSONB shape (mirrors the agent's YAML + body):
-- {
--   "metadata": {
--     "source_type": "blog|substack|lab|arxiv|medium",
--     "url": "...",
--     "publication": "...",
--     "author": "...",
--     "title": "...",
--     "published_at": "YYYY-MM-DD",
--     "ingested_at": "<ISO 8601>",
--     "topics": ["slug1", "slug2"],
--     "relevance_score": 8,
--     "slot": "morning"
--   },
--   "sections": {
--     "tldr": "...",
--     "author_background_bias": "...",
--     "whats_new": "...",
--     "counterintuitive_claims": "...",
--     "steelman": "...",
--     "steelman_rebuttal": "...",
--     "forward_looking_hypotheses": "...",
--     "technical_insights": "...",
--     "key_assumptions": "...",
--     "second_order_implications": "...",
--     "my_take": "...",
--     "talking_points": "..."
--   }
-- }

CREATE TABLE posts (
  id                  BIGSERIAL PRIMARY KEY,
  source_id           INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  url                 TEXT UNIQUE NOT NULL,
  title               TEXT,
  author              TEXT,
  published_at        TIMESTAMPTZ,
  fetched_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  full_text           TEXT,
  embedding           vector(1536),
  structured_analysis JSONB,
  topics              TEXT[] NOT NULL DEFAULT '{}',
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX posts_published_at_idx ON posts (published_at DESC NULLS LAST);
CREATE INDEX posts_topics_gin_idx   ON posts USING GIN (topics);
-- Cosine ANN index for semantic similarity (rebuild after bulk load):
--   REINDEX INDEX posts_embedding_idx;
CREATE INDEX posts_embedding_idx    ON posts USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ----- per-user post scores --------------------------------------------

CREATE TABLE user_post_scores (
  user_id    TEXT   NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  post_id    BIGINT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  score      SMALLINT NOT NULL CHECK (score BETWEEN 0 AND 10),    -- agent prediction (was relevance_score)
  user_score SMALLINT CHECK (user_score IS NULL OR user_score BETWEEN 0 AND 10),  -- user rating (was tim_score)
  agent_blurb TEXT,
  ranked_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, post_id)
);

CREATE INDEX user_post_scores_feed_idx ON user_post_scores (user_id, score DESC, ranked_at DESC);

-- ----- user signals (thumbs / saves / archives / opens / dwell) -------

CREATE TABLE user_signals (
  id         BIGSERIAL PRIMARY KEY,
  user_id    TEXT   NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  post_id    BIGINT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  kind       TEXT NOT NULL CHECK (kind IN (
                'up','down','save','archive','open',
                'dwell_ms','more_like_this','less_like_source'
             )),
  value      BIGINT,                                                -- for dwell_ms; null otherwise
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX user_signals_user_idx      ON user_signals (user_id, created_at DESC);
CREATE INDEX user_signals_user_post_idx ON user_signals (user_id, post_id);

-- ----- jobs (async curator runs) ---------------------------------------

CREATE TABLE jobs (
  id          BIGSERIAL PRIMARY KEY,
  user_id     TEXT REFERENCES users(id) ON DELETE CASCADE,
  kind        TEXT NOT NULL,                                        -- 'curate','backfill','sync', etc.
  state       TEXT NOT NULL DEFAULT 'queued' CHECK (state IN (
                'queued','running','succeeded','failed','cancelled'
             )),
  started_at  TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  error       TEXT,
  payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX jobs_user_state_idx ON jobs (user_id, state, created_at DESC);

-- ----- per-user agent profile state ------------------------------------
-- Mirrors files the Managed Agent maintains in the shared staging git repo
-- under users/<user_id>/_profile/ (deltas.md, evolution.md, etc.).
-- Decomposed into proper tables in a later milestone if query patterns
-- demand it. M2-canonicalization-direction TBD per SPEC §"Storage transport".

CREATE TABLE user_profile_state (
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind       TEXT NOT NULL CHECK (kind IN (
                'deltas','evolution','discovered_sources',
                'feed_map','pinned_sources','feedback'
             )),
  content    TEXT,                                                  -- markdown for prose, JSON-as-text for feed_map
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, kind)
);
