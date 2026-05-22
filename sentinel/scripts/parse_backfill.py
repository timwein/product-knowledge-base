#!/usr/bin/env python3
"""Parse the cleared kb-blog-curator analyses into a JSONL of post rows.

Reads the drop list from sentinel/backfill/personal-finance-candidates.md
(Tim strikes through any heading he wants to keep) and emits one JSON
object per kept analysis to sentinel/backfill/posts.jsonl.

Usage:
    python sentinel/scripts/parse_backfill.py <path-to-tweet-knowledge-base>

The output JSONL is the input for the loader (built next) that upserts
into Postgres `posts` + per-user `user_post_scores` on signup.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

# Make the curator package importable without installation.
THIS = Path(__file__).resolve()
REPO = THIS.parents[2]
sys.path.insert(0, str(REPO / "sentinel" / "curator"))

from sentinel_curator.backfill import load_drop_list, parse_directory  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    kb_root = Path(sys.argv[1]).resolve()
    if not kb_root.is_dir():
        print(f"not a directory: {kb_root}", file=sys.stderr)
        return 2

    sentinel_root = REPO / "sentinel"
    drop_list_path = sentinel_root / "backfill" / "personal-finance-candidates.md"
    output_path = sentinel_root / "backfill" / "posts.jsonl"

    drops = load_drop_list(drop_list_path)
    print(f"loaded {len(drops)} drop entries from {drop_list_path.name}", file=sys.stderr)

    count = 0
    with output_path.open("w", encoding="utf-8") as out:
        for parsed in parse_directory(kb_root, drop_paths=drops):
            row = asdict(parsed)
            out.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            out.write("\n")
            count += 1

    print(f"wrote {count} post rows to {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
