#!/usr/bin/env python3
"""Load the parsed backfill posts.jsonl into Postgres (one-time admin task).

Per-user user_post_scores rows are NOT created here — those happen at
signup via apply_backfill_to_user inside the curator API.

Usage:
    DATABASE_URL=postgres://... python sentinel/scripts/load_backfill_posts.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

THIS = Path(__file__).resolve()
REPO = THIS.parents[2]
sys.path.insert(0, str(REPO / "sentinel" / "curator"))

from sentinel_curator.db import connect  # noqa: E402
from sentinel_curator.backfill_loader import load_posts  # noqa: E402


async def main() -> None:
    jsonl = REPO / "sentinel" / "backfill" / "posts.jsonl"
    if not jsonl.exists():
        print(f"missing {jsonl} — run sentinel/scripts/parse_backfill.py first",
              file=sys.stderr)
        sys.exit(2)
    conn = await connect()
    try:
        result = await load_posts(conn, jsonl)
    finally:
        await conn.close()
    print(
        f"input_rows={result['input_rows']} "
        f"deduped={result['deduped_rows']} "
        f"inserted={result['inserted']} "
        f"updated={result['updated']}"
    )


if __name__ == "__main__":
    asyncio.run(main())
