#!/usr/bin/env python3
"""Load a seed corpus YAML file into Postgres.

Usage:
    DATABASE_URL=postgres://... python sentinel/scripts/load_seed_corpus.py sentinel/seed-corpora/ai.yaml

Idempotent — re-running upserts the same corpus + sources.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

THIS = Path(__file__).resolve()
REPO = THIS.parents[2]
sys.path.insert(0, str(REPO / "sentinel" / "curator"))

from sentinel_curator.db import connect  # noqa: E402
from sentinel_curator.seed_loader import load_corpus, parse_seed_yaml  # noqa: E402


async def main(yaml_path: Path) -> None:
    corpus = parse_seed_yaml(yaml_path)
    print(f"loaded {len(corpus.sources)} sources from {yaml_path.name}")
    conn = await connect()
    try:
        result = await load_corpus(conn, corpus)
    finally:
        await conn.close()
    print(f"corpus_id={result['corpus_id']} "
          f"sources_upserted={result['sources_upserted']} "
          f"joins_inserted={result['joins_inserted']}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    asyncio.run(main(Path(sys.argv[1]).resolve()))
