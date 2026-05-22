"""Shared utilities — URL canonicalization, etc."""

from __future__ import annotations

from urllib.parse import urlparse


def canonical_host(url: str) -> str:
    """Lowercased host with leading 'www.' stripped. Empty string on parse failure."""
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def canonical_source_url(url: str) -> str:
    """Source-level URL: scheme://host/, used as the dedupe key for `sources.url`."""
    host = canonical_host(url)
    if not host:
        return url
    return f"https://{host}/"
