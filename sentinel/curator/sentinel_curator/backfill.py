"""Parse existing kb-blog-curator analyses into Sentinel post rows.

Reads blog-*.md files written by the existing single-user curator (in
tweet-knowledge-base) and emits dictionaries shaped for upsert into the
posts + user_post_scores tables.

Each input file has the structure:

    # [Article Title](https://source-url/...)
    *By Author · Publication · Published YYYY-MM-DD*

    <details><summary>Metadata · ...</summary>

    ```yaml
    source_type: blog
    url: "..."
    publication: "..."
    author: "..."
    title: "..."
    published_at: "YYYY-MM-DD"
    ingested_at: "..."
    topics: ["...", "..."]
    relevance_score: 8
    tim_score:
    slot: morning
    ```

    </details>

    ---

    ## TLDR
    ...body...

    ---

    ## Author Background & Bias
    ...
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

# Mapping H2 section headers (lowercased) → JSON keys for structured_analysis.sections.
SECTION_KEY_MAP: dict[str, str] = {
    "tldr": "tldr",
    "tl;dr": "tldr",
    "author background & bias": "author_background_bias",
    "author background and bias": "author_background_bias",
    "what's new / non-obvious": "whats_new",
    "whats new / non-obvious": "whats_new",
    "what's new": "whats_new",
    "counterintuitive claims": "counterintuitive_claims",
    "steelman": "steelman",
    "steelman rebuttal": "steelman_rebuttal",
    "forward-looking hypotheses": "forward_looking_hypotheses",
    "forward looking hypotheses": "forward_looking_hypotheses",
    "technical insights": "technical_insights",
    "key assumptions": "key_assumptions",
    "second-order implications": "second_order_implications",
    "second order implications": "second_order_implications",
    "my take": "my_take",
    "talking points": "talking_points",
}


@dataclass
class ParsedPost:
    """One row's worth of post data, ready for DB upsert."""

    url: str
    title: str | None
    author: str | None
    publication: str | None
    published_at: str | None  # ISO date string
    topics: list[str]
    relevance_score: int | None
    structured_analysis: dict  # {metadata: {...}, sections: {...}}
    source_path: str  # for traceability


_H1_LINK_RE = re.compile(r"^#\s+\[([^\]]+)\]\(([^)]+)\)\s*$")
_YAML_BLOCK_RE = re.compile(
    r"<details>.*?```yaml\s*\n(.*?)\n```\s*</details>", re.DOTALL
)
# Older analyses use Jekyll-style leading frontmatter: ---\n<yaml>\n---\n
_JEKYLL_FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _extract_title_and_url(text: str) -> tuple[str | None, str | None]:
    for line in text.splitlines():
        m = _H1_LINK_RE.match(line)
        if m:
            return m.group(1).strip(), m.group(2).strip()
        if line.startswith("# "):
            # H1 present but no link — strip and return title only.
            return line[2:].strip(), None
    return None, None


def _extract_yaml(text: str) -> dict:
    # Preferred format: <details><summary>...</summary>\n```yaml\n...\n```\n</details>
    m = _YAML_BLOCK_RE.search(text)
    if not m:
        # Fallback: Jekyll-style leading frontmatter on older analyses.
        m = _JEKYLL_FM_RE.match(text)
    if not m:
        return {}
    raw = m.group(1)
    try:
        parsed = yaml.safe_load(raw) or {}
        if isinstance(parsed, dict):
            return parsed
        return {}
    except yaml.YAMLError:
        return {}


def _strip_yaml_block(text: str) -> str:
    """Remove the YAML frontmatter (either format) so it doesn't end up in sections."""
    stripped = _YAML_BLOCK_RE.sub("", text)
    stripped = _JEKYLL_FM_RE.sub("", stripped, count=1)
    return stripped


def _extract_sections(text: str) -> dict[str, str]:
    """Split body on H2 headers and return {section_key: body_markdown}."""
    body = _strip_yaml_block(text)
    sections: dict[str, str] = {}
    h2_matches = list(_H2_RE.finditer(body))
    for idx, m in enumerate(h2_matches):
        name = m.group(1).strip().lower().rstrip(":")
        start = m.end()
        end = h2_matches[idx + 1].start() if idx + 1 < len(h2_matches) else len(body)
        block = body[start:end].strip()
        # Strip trailing horizontal rule that separates sections.
        if block.endswith("---"):
            block = block[:-3].rstrip()
        key = SECTION_KEY_MAP.get(name)
        if key:
            sections[key] = block
        else:
            # Preserve unrecognized sections under a slug to avoid silent loss.
            slug = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
            if slug:
                sections.setdefault("_extra", {})  # type: ignore[assignment]
                # _extra value is a dict of slug → body
                extra = sections["_extra"]  # type: ignore[assignment]
                assert isinstance(extra, dict)
                extra[slug] = block
    return sections


def parse_file(path: Path) -> ParsedPost | None:
    """Parse a single blog-*.md file. Returns None if structure is unparseable."""
    text = path.read_text(encoding="utf-8", errors="replace")
    meta = _extract_yaml(text)
    title_from_h1, url_from_h1 = _extract_title_and_url(text)

    url = meta.get("url") or url_from_h1
    if not url:
        return None  # no URL, can't be a valid post row

    title = meta.get("title") or title_from_h1
    publication = meta.get("publication")
    author = meta.get("author")
    published_at = meta.get("published_at")
    topics_raw = meta.get("topics") or []
    topics: list[str] = []
    if isinstance(topics_raw, list):
        topics = [str(t).strip() for t in topics_raw if t]
    relevance = meta.get("relevance_score")
    if isinstance(relevance, str):
        try:
            relevance = int(relevance)
        except ValueError:
            relevance = None

    sections = _extract_sections(text)

    # Strip tim_score from metadata before storing — it lived per-user, not per-post.
    metadata_clean = {
        k: v
        for k, v in meta.items()
        if k != "tim_score"
    }

    structured_analysis = {
        "metadata": metadata_clean,
        "sections": sections,
    }

    return ParsedPost(
        url=url,
        title=str(title).strip() if title else None,
        author=str(author).strip() if author else None,
        publication=str(publication).strip() if publication else None,
        published_at=str(published_at).strip() if published_at else None,
        topics=topics,
        relevance_score=relevance if isinstance(relevance, int) else None,
        structured_analysis=structured_analysis,
        source_path=str(path),
    )


def parse_directory(
    root: Path,
    drop_paths: set[str] | None = None,
) -> Iterable[ParsedPost]:
    """Walk blog-*.md files under root/2026/**/, skipping any in drop_paths.

    drop_paths is a set of paths relative to root (e.g.
    "2026/04/13/blog-platformer-altman-second-thoughts.md").
    """
    drop = drop_paths or set()
    for path in sorted(root.glob("2026/**/blog-*.md")):
        if path.name.startswith("blog-synthesis"):
            continue
        rel = str(path.relative_to(root))
        if rel in drop:
            continue
        parsed = parse_file(path)
        if parsed is not None:
            yield parsed


def load_drop_list(md_path: Path) -> set[str]:
    """Parse the personal-finance candidates markdown for unstruck headings.

    Convention from sentinel/backfill/personal-finance-candidates.md:
        ### `2026/04/13/blog-foo.md`    → drop (un-struck)
        ~~### `2026/04/13/blog-foo.md`~~ → keep (struck through)
    """
    if not md_path.exists():
        return set()
    text = md_path.read_text(encoding="utf-8")
    drop: set[str] = set()
    for line in text.splitlines():
        s = line.strip()
        # Tilde-struck lines are kept — skip them.
        if s.startswith("~~### ") or s.startswith("~~###`"):
            continue
        m = re.match(r"^###\s+`([^`]+)`\s*$", s)
        if m:
            drop.add(m.group(1))
    return drop
