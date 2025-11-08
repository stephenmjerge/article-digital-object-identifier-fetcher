"""Asynchronous ingestion pipeline that orchestrates metadata + PDF fetching."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import structlog

from adoif.models import ArticleMetadata, Author, FetchRequest, StoredArtifact
from adoif.utils import extract_doi, slugify
from .pdf_fetcher import PDFFetcher
from .resolvers import ResolverRegistry
from .storage import LibraryStorage

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class ManualOverrides:
    """Optional user-provided metadata used when resolvers fail."""

    title: str | None = None
    journal: str | None = None
    tags: Sequence[str] = ()


@dataclass(slots=True)
class IngestOutcome:
    artifact: StoredArtifact
    created: bool
    pdf_downloaded: bool


class IngestError(RuntimeError):
    """Raised when ingestion cannot proceed."""


class IngestPipeline:
    """Coordinates metadata resolution, PDF fetching, and persistence."""

    def __init__(
        self,
        registry: ResolverRegistry,
        storage: LibraryStorage,
        pdf_fetcher: PDFFetcher | None = None,
    ) -> None:
        self._registry = registry
        self._storage = storage
        self._pdf_fetcher = pdf_fetcher

    async def ingest(
        self,
        request: FetchRequest,
        overrides: ManualOverrides | None = None,
        *,
        persist: bool = True,
    ) -> IngestOutcome:
        metadata = await self._resolve_metadata(request, overrides)
        artifact = StoredArtifact(metadata=metadata)

        pdf_downloaded = False
        if persist and self._pdf_fetcher and metadata.doi:
            temp_path = self._storage.temp_pdf_path(metadata.doi)
            download = await self._pdf_fetcher.fetch(metadata.doi, temp_path)
            if download:
                final_path, checksum = await self._storage.register_pdf(
                    doi=metadata.doi,
                    temp_path=download.path,
                    source=download.source,
                    license=download.license,
                )
                artifact.pdf_path = final_path
                artifact.checksum = checksum
                pdf_downloaded = True

        created = False
        if persist:
            existing = await self._storage.find_by_doi(metadata.doi)
            created = existing is None
            await self._storage.upsert(artifact)

        return IngestOutcome(artifact=artifact, created=created, pdf_downloaded=pdf_downloaded)

    async def _resolve_metadata(
        self, request: FetchRequest, overrides: ManualOverrides | None
    ) -> ArticleMetadata:
        result = await self._registry.resolve(request)
        metadata = result.metadata if result else None
        if metadata is None:
            metadata = self._metadata_from_overrides(request, overrides)
        elif overrides:
            metadata = metadata.model_copy()
            if overrides.title:
                metadata.title = overrides.title
            if overrides.journal:
                metadata.journal = overrides.journal
            if overrides.tags:
                metadata.tags = sorted(set(metadata.tags).union(overrides.tags))
        return metadata

    def _metadata_from_overrides(
        self, request: FetchRequest, overrides: ManualOverrides | None
    ) -> ArticleMetadata:
        if not overrides or not overrides.title:
            raise IngestError(
                "No resolvers returned metadata and no --title was supplied. "
                "Specify --title to create a manual record."
            )
        doi = extract_doi(request.identifier)
        if not doi:
            doi = f"manual-{slugify(request.identifier)}"
        return ArticleMetadata(
            doi=doi,
            title=overrides.title,
            journal=overrides.journal,
            tags=list(overrides.tags),
            authors=[Author(given_name="Unknown", family_name="Author")],
        )
