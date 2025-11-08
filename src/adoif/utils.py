"""Utility helpers for identifier normalization and filesystem-safe names."""

from __future__ import annotations

import re
import unicodedata

DOI_PATTERN = re.compile(r"(10\.\d{4,9}/[\w.;()/:+-]+)", flags=re.IGNORECASE)
SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def extract_doi(identifier: str) -> str | None:
    """Return a normalized DOI if the identifier contains one."""
    if not identifier:
        return None
    match = DOI_PATTERN.search(identifier.strip())
    if not match:
        return None
    doi = match.group(1)
    return doi.lower()


def is_probable_doi(identifier: str) -> bool:
    """Check if the identifier looks like a DOI."""
    return extract_doi(identifier) is not None


def slugify(value: str, max_length: int = 80) -> str:
    """Create a filesystem-safe slug."""
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = value.lower()
    value = SLUG_PATTERN.sub("-", value).strip("-")
    if not value:
        value = "item"
    return value[:max_length]
