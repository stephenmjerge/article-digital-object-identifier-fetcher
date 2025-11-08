"""Citation export helpers."""

from __future__ import annotations

import json
from datetime import datetime

from adoif.models import StoredArtifact
from adoif.utils import slugify


def export_bibtex(artifacts: list[StoredArtifact]) -> str:
    entries = [artifact_to_bibtex(artifact) for artifact in artifacts]
    return "\n\n".join(entries)


def artifact_to_bibtex(artifact: StoredArtifact) -> str:
    metadata = artifact.metadata
    key = slugify(metadata.title or metadata.doi or "adoif")
    authors = " and ".join(
        [
            " ".join(part for part in (author.given_name, author.family_name) if part).strip()
            for author in metadata.authors
            if author.full_name.strip()
        ]
    )
    year = metadata.publication_date.year if metadata.publication_date else ""
    fields = {
        "title": metadata.title or "Untitled",
        "author": authors,
        "journal": metadata.journal or "",
        "year": year,
        "doi": metadata.doi,
    }
    body = ",\n".join(
        f"  {field} = {{{value}}}" for field, value in fields.items() if value
    )
    return f"@article{{{key},\n{body}\n}}"


def export_csl_json(artifacts: list[StoredArtifact]) -> str:
    payload = [artifact_to_csl(artifact) for artifact in artifacts]
    return json.dumps(payload, indent=2)


def artifact_to_csl(artifact: StoredArtifact) -> dict:
    metadata = artifact.metadata
    date_parts: list[list[int]] = []
    if metadata.publication_date:
        date_parts = [[metadata.publication_date.year]]
        if metadata.publication_date.month:
            date_parts[0].append(metadata.publication_date.month)
        if metadata.publication_date.day:
            date_parts[0].append(metadata.publication_date.day)
    return {
        "id": metadata.doi or slugify(metadata.title or "adoif"),
        "type": "article-journal",
        "title": metadata.title,
        "DOI": metadata.doi,
        "container-title": metadata.journal,
        "author": [
            {"given": author.given_name, "family": author.family_name}
            for author in metadata.authors
        ],
        "issued": {"date-parts": date_parts} if date_parts else None,
    }
