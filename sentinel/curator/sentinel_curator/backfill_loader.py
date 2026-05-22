"""Load the parsed posts.jsonl into the global posts table.

This is a one-time admin task: take Tim's existing 357 cleared analyses
and upsert them into Sentinel's `posts` table (shared across users).
Per-user backfill of `user_post_scores` happens at signup time via a
separate call (see `apply_backfill_to_user`).

Dedupe rule: if the same URL appears multiple times in posts.jsonl
(11 URLs do), keep the row with the latest `ingested_at` from its
structured_analysis metadata.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from asyncpg import Connection

from .util import canonical_source_url


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # Accept "YYYY-MM-DD" and full ISO 8601.
        if len(value) == 10:
            return datetime.fromisoformat(value)
        # Tolerate trailing Z.
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _dedupe(rows: list[dict]) -> list[dict]:
    """Keep the latest-ingested row per URL."""
    best: dict[str, dict] = {}
    for r in rows:
        url = r["url"]
        ingested = r["structured_analysis"]["metadata"].get("ingested_at")
        if url not in best:
            best[url] = r
            continue
        existing = best[url]["structured_analysis"]["metadata"].get("ingested_at")
        if (ingested or "") > (existing or ""):
            best[url] = r
    return list(best.values())


async def _ensure_source(conn: Connection, post_url: str, publication: str | None) -> int:
    """Upsert a sources row keyed on host. Return source_id."""
    src_url = canonical_source_url(post_url)
    return await conn.fetchval(
        """
        INSERT INTO sources (kind, url, title)
        VALUES ('blog', $1, $2)
        ON CONFLICT (url) DO UPDATE
          SET title = COALESCE(sources.title, EXCLUDED.title)
        RETURNING id
        """,
        src_url,
        publication,
    )


async def load_posts(conn: Connection, jsonl_path: Path) -> dict[str, int]:
    """Upsert all rows from posts.jsonl into the posts table.

    Returns counts. Idempotent — running twice produces the same end state.
    """
    rows: list[dict] = []
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    deduped = _dedupe(rows)

    inserted = 0
    updated = 0
    for row in deduped:
        source_id = await _ensure_source(conn, row["url"], row.get("publication"))
        published_at = _parse_iso(row.get("published_at"))

        result = await conn.fetchrow(
            """
            INSERT INTO posts (
                source_id, url, title, author, published_at,
                full_text, structured_analysis, topics
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
            ON CONFLICT (url) DO UPDATE
              SET title               = EXCLUDED.title,
                  author              = EXCLUDED.author,
                  published_at        = EXCLUDED.published_at,
                  structured_analysis = EXCLUDED.structured_analysis,
                  topics              = EXCLUDED.topics
            RETURNING xmax = 0 AS inserted
            """,
            source_id,
            row["url"],
            row.get("title"),
            row.get("author"),
            published_at,
            None,  # full_text — backfill posts don't carry extracted text
            json.dumps(row["structured_analysis"]),
            row.get("topics") or [],
        )
        if result["inserted"]:
            inserted += 1
        else:
            updated += 1

    return {
        "input_rows": len(rows),
        "deduped_rows": len(deduped),
        "inserted": inserted,
        "updated": updated,
    }


async def apply_backfill_to_user(conn: Connection, user_id: str) -> int:
    """Create user_post_scores rows for every backfilled post for this user.

    Uses the relevance_score from structured_analysis.metadata as score,
    same value for every user (verbatim backfill per SPEC §"Backfill").
    Returns the number of rows inserted (0 on re-runs — ON CONFLICT skips).
    """
    return await conn.fetchval(
        """
        WITH inserted AS (
          INSERT INTO user_post_scores (user_id, post_id, score, agent_blurb)
          SELECT
              $1::text,
              p.id,
              GREATEST(0, LEAST(10,
                  COALESCE(
                      (p.structured_analysis -> 'metadata' ->> 'relevance_score')::int,
                      5
                  )
              ))::smallint,
              p.structured_analysis -> 'sections' ->> 'tldr'
          FROM posts p
          WHERE p.structured_analysis IS NOT NULL
          ON CONFLICT (user_id, post_id) DO NOTHING
          RETURNING 1
        )
        SELECT count(*)::int FROM inserted
        """,
        user_id,
    )
