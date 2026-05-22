#!/usr/bin/env python3
"""Scan blog analyses in tweet-knowledge-base for personal-finance mentions.

Per SPEC §"Backfill", the 468 existing blog-*.md files are backfilled
verbatim for new Sentinel users EXCEPT analyses that discuss Tim's
personal financial exposure (Anthropic equity, stake, portfolio,
Anthropic valuation in a personal-investment context).

This scanner walks the corpus, flags candidates with keyword matches in
two tiers, and emits a Markdown report for Tim's eyeball review.

Usage:
    python scan_personal_finance_backfill.py <path-to-tweet-knowledge-base>

Output is written to sentinel/backfill/personal-finance-candidates.md
relative to the repo root (computed from this script's location).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Tier 1 — definite flags. Phrases that strongly indicate Tim's personal
# financial exposure to Anthropic or other investments. Recommend DROP.
TIER_1_PATTERNS = [
    r"\bmy\s+anthropic\b",
    r"\btim'?s\s+anthropic\b",
    r"\btim\s+weingarten'?s\s+(?:equity|stake|portfolio|position|holdings?)\b",
    r"\bmy\s+(?:equity|stake|portfolio|position|holdings?)\s+in\s+anthropic\b",
    r"\bmy\s+anthropic\s+(?:equity|stake|position|holdings?|shares?)\b",
    r"\bpersonal\s+(?:stake|investment|portfolio|holdings?)\s+in\s+anthropic\b",
    r"\b(?:as|since)\s+(?:i|tim)\s+(?:hold|own|invest)\b",
    r"\b(?:i|tim)\s+(?:hold|own)\s+(?:anthropic|equity)\b",
]

# Tier 2 — flag for review. Proximity-based: terms that appear in both
# public commentary AND personal-finance contexts. Tim eyeballs each.
TIER_2_PATTERNS = [
    r"\banthropic'?s?\s+valuation\b",
    r"\bvaluation\s+of\s+anthropic\b",
    r"\banthropic\s+(?:secondaries|secondary\s+(?:market|sale))\b",
    r"\bsecondaries?\s+(?:in|on|at)\s+anthropic\b",
    r"\bfounders\s+fund.{0,80}\banthropic\b",
    r"\banthropic.{0,80}\bfounders\s+fund\b",
    r"\bweingarten\b",
    r"\b(?:my|tim'?s)\s+portfolio\b",
    # Specific valuation figures near "anthropic" (heuristic — public
    # commentary often mentions these, but worth eyeball)
    r"\$\d{2,4}\s*(?:billion|b)\b.{0,80}\banthropic\b",
    r"\banthropic\b.{0,80}\$\d{2,4}\s*(?:billion|b)\b",
]


def find_matches(text: str, patterns: list[str]) -> list[tuple[int, str, str]]:
    """Return (line_no, snippet, context_line) tuples for each match."""
    out: list[tuple[int, str, str]] = []
    lines = text.splitlines()
    text_low = text.lower()
    for pat in patterns:
        for m in re.finditer(pat, text_low, flags=re.IGNORECASE | re.DOTALL):
            line_no = text[: m.start()].count("\n") + 1
            snippet = m.group(0)
            context_line = lines[line_no - 1] if line_no - 1 < len(lines) else ""
            out.append((line_no, snippet, context_line.strip()))
    return out


def scan_file(path: Path) -> dict[str, list[tuple[int, str, str]]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "tier1": find_matches(text, TIER_1_PATTERNS),
        "tier2": find_matches(text, TIER_2_PATTERNS),
    }


def render_report(
    root: Path,
    files: list[Path],
    tier1_hits: list[tuple[Path, list[tuple[int, str, str]]]],
    tier2_hits: list[tuple[Path, list[tuple[int, str, str]]]],
) -> str:
    total = len(files)
    t1_n = len(tier1_hits)
    t2_n = len(tier2_hits)
    clean_n = total - t1_n - t2_n

    parts: list[str] = []
    parts.append("# Backfill candidate-drop list — personal-finance scan")
    parts.append("")
    parts.append(
        f"Scanned **{total}** `blog-*.md` files in "
        f"`tweet-knowledge-base/2026/**/`."
    )
    parts.append("")
    parts.append(f"- **Tier 1 — recommended drops:** {t1_n} file(s)")
    parts.append(
        f"- **Tier 2 — needs review:** {t2_n} file(s) "
        f"(may be public commentary OR personal context)"
    )
    parts.append(f"- **Clean (ship as-is in backfill):** {clean_n} file(s)")
    parts.append("")
    parts.append(
        "Review process: Tim eyeballs each Tier 1 and Tier 2 entry below "
        "and edits this file inline — strike through the heading "
        "(`~~### path~~`) for any file that should ship despite the "
        "match. Anything left un-struck is dropped from the backfill."
    )
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("## Tier 1 — recommended drops")
    parts.append("")
    if not tier1_hits:
        parts.append("_None found._")
    else:
        for path, hits in tier1_hits:
            rel = path.relative_to(root)
            parts.append(f"### `{rel}`")
            parts.append("")
            seen: set[tuple[int, str]] = set()
            for line_no, snippet, context in hits[:8]:
                key = (line_no, snippet.lower())
                if key in seen:
                    continue
                seen.add(key)
                parts.append(f"- **L{line_no}** match `{snippet}`")
                if context:
                    parts.append(f"  > {context[:200]}")
            parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("## Tier 2 — review")
    parts.append("")
    if not tier2_hits:
        parts.append("_None found._")
    else:
        for path, hits in tier2_hits:
            rel = path.relative_to(root)
            parts.append(f"### `{rel}`")
            parts.append("")
            seen = set()
            for line_no, snippet, context in hits[:8]:
                key = (line_no, snippet.lower())
                if key in seen:
                    continue
                seen.add(key)
                parts.append(f"- **L{line_no}** match `{snippet}`")
                if context:
                    parts.append(f"  > {context[:200]}")
            parts.append("")
    return "\n".join(parts) + "\n"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    files = sorted(
        p
        for p in root.glob("2026/**/blog-*.md")
        if not p.name.startswith("blog-synthesis")
    )
    if not files:
        print(f"no blog-*.md files found under {root}/2026/", file=sys.stderr)
        return 2

    tier1_hits: list[tuple[Path, list[tuple[int, str, str]]]] = []
    tier2_hits: list[tuple[Path, list[tuple[int, str, str]]]] = []

    for f in files:
        m = scan_file(f)
        if m["tier1"]:
            tier1_hits.append((f, m["tier1"]))
        elif m["tier2"]:
            tier2_hits.append((f, m["tier2"]))

    report = render_report(root, files, tier1_hits, tier2_hits)

    # Emit to stdout; caller redirects to file.
    sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
