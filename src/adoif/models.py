"""Core data models used throughout the ADOIF application."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class Author(BaseModel):
    """Represents a single contributor to an article."""

    given_name: str
    family_name: str
    affiliation: str | None = None

    @property
    def full_name(self) -> str:
        return " ".join(part for part in (self.given_name, self.family_name) if part)


class ArticleMetadata(BaseModel):
    """Normalized metadata describing an academic work."""

    doi: str
    title: str
    authors: list[Author] = Field(default_factory=list)
    journal: str | None = None
    abstract: str | None = None
    publication_date: datetime | None = None
    url: str | None = None
    tags: list[str] = Field(default_factory=list)
    source_payload: dict[str, Any] = Field(default_factory=dict)


class FetchRequest(BaseModel):
    """User-initiated request to ingest a new article."""

    identifier: str  # DOI, PMID, or free-text query
    created_at: datetime = Field(default_factory=datetime.utcnow)
    allow_cached: bool = True


class FetchResult(BaseModel):
    """Outcome of a resolver attempt."""

    metadata: ArticleMetadata
    provider: str
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    fetched_at: datetime = Field(default_factory=datetime.utcnow)


class StoredArtifact(BaseModel):
    """Represents an item persisted to the local research library."""

    metadata: ArticleMetadata
    pdf_path: Path | None = None
    text_path: Path | None = None
    checksum: str | None = None
    stored_at: datetime = Field(default_factory=datetime.utcnow)
