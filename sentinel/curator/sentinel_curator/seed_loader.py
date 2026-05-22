"""Load a seed corpus YAML file into the DB.

Upserts:
  - one row in seed_corpora (slug, name, description)
  - one row in sources per listed source (url, title, feed_url)
  - join rows in seed_corpus_sources
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from asyncpg import Connection

from .util import canonical_source_url


@dataclass
class SeedSource:
    url: str
    title: str | None
    feed_url: str | None
    topics: list[str]


@dataclass
class SeedCorpus:
    slug: str
    name: str
    description: str | None
    sources: list[SeedSource]


def parse_seed_yaml(path: Path) -> SeedCorpus:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} did not parse to a YAML mapping")
    sources_raw = raw.get("sources") or []
    sources: list[SeedSource] = []
    for s in sources_raw:
        if not isinstance(s, dict):
            continue
        sources.append(
            SeedSource(
                url=canonical_source_url(str(s["url"])),
                title=str(s["title"]) if s.get("title") else None,
                feed_url=str(s["feed_url"]) if s.get("feed_url") else None,
                topics=list(s.get("topics") or []),
            )
        )
    return SeedCorpus(
        slug=str(raw["slug"]),
        name=str(raw["name"]),
        description=str(raw["description"]) if raw.get("description") else None,
        sources=sources,
    )


async def load_corpus(conn: Connection, corpus: SeedCorpus) -> dict[str, int]:
    """Upsert a seed corpus and its sources. Returns counts."""
    corpus_id = await conn.fetchval(
        """
        INSERT INTO seed_corpora (slug, name, description)
        VALUES ($1, $2, $3)
        ON CONFLICT (slug) DO UPDATE
          SET name = EXCLUDED.name,
              description = EXCLUDED.description
        RETURNING id
        """,
        corpus.slug,
        corpus.name,
        corpus.description,
    )

    inserted_sources = 0
    inserted_joins = 0
    for src in corpus.sources:
        source_id = await conn.fetchval(
            """
            INSERT INTO sources (kind, url, feed_url, title)
            VALUES ('blog', $1, $2, $3)
            ON CONFLICT (url) DO UPDATE
              SET feed_url = COALESCE(EXCLUDED.feed_url, sources.feed_url),
                  title    = COALESCE(EXCLUDED.title, sources.title)
            RETURNING id
            """,
            src.url,
            src.feed_url,
            src.title,
        )
        inserted_sources += 1

        result = await conn.execute(
            """
            INSERT INTO seed_corpus_sources (corpus_id, source_id)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
            """,
            corpus_id,
            source_id,
        )
        if result.endswith(" 1"):
            inserted_joins += 1

    return {
        "corpus_id": corpus_id,
        "sources_upserted": inserted_sources,
        "joins_inserted": inserted_joins,
    }
