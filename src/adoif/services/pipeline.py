"""Asynchronous ingestion pipeline that orchestrates metadata + PDF fetching."""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path
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
    pdf_saved: bool


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
        local_pdf: Path | None = None,
    ) -> IngestOutcome:
        metadata = await self._resolve_metadata(request, overrides)
        artifact = StoredArtifact(metadata=metadata)

        pdf_saved = False
        if persist and metadata.doi:
            if local_pdf is not None:
                pdf_saved = await self._attach_local_pdf(metadata.doi, local_pdf, artifact)
            elif self._pdf_fetcher:
                pdf_saved = await self._download_pdf(metadata.doi, artifact)

        created = False
        if persist:
            existing = await self._storage.find_by_doi(metadata.doi)
            created = existing is None
            await self._storage.upsert(artifact)

        return IngestOutcome(artifact=artifact, created=created, pdf_saved=pdf_saved)

    async def _attach_local_pdf(self, doi: str, source_path: Path, artifact: StoredArtifact) -> bool:
        temp_path = self._storage.temp_pdf_path(doi)
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copyfile, source_path, temp_path)
        final_path, checksum = await self._storage.register_pdf(
            doi=doi,
            temp_path=temp_path,
            source="manual-upload",
            license=None,
            host_type="local",
        )
        artifact.pdf_path = final_path
        artifact.checksum = checksum
        return True

    async def _download_pdf(self, doi: str, artifact: StoredArtifact) -> bool:
        if not self._pdf_fetcher:
            return False
        temp_path = self._storage.temp_pdf_path(doi)
        download = await self._pdf_fetcher.fetch(doi, temp_path)
        if not download:
            return False
        final_path, checksum = await self._storage.register_pdf(
            doi=doi,
            temp_path=download.path,
            source=download.source,
            license=download.license,
            host_type=download.host_type,
        )
        artifact.pdf_path = final_path
        artifact.checksum = checksum
        return True

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
