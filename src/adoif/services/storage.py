"""Storage interfaces for the local research library."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Protocol

import structlog

from adoif.models import StoredArtifact
from adoif.settings import Settings
from adoif.utils import slugify

logger = structlog.get_logger(__name__)


class LibraryStorage(Protocol):
    """High-level contract for persisting artifacts."""

    async def upsert(self, artifact: StoredArtifact) -> StoredArtifact:
        ...

    async def find_by_doi(self, doi: str) -> StoredArtifact | None:
        ...

    async def list_artifacts(self) -> list[StoredArtifact]:
        ...

    def pdf_path_for(self, doi: str) -> Path:
        ...


class LocalLibrary(LibraryStorage):
    """Minimal placeholder implementation that simulates persistence."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = asyncio.Lock()
        self._memory_store: dict[str, StoredArtifact] = {}
        self._index_path = self._settings.data_dir / "library-index.json"
        self._pdf_dir = self._settings.data_dir / "pdfs"
        self._settings.ensure_directories()
        self._pdf_dir.mkdir(parents=True, exist_ok=True)
        self._load_from_disk()

    async def upsert(self, artifact: StoredArtifact) -> StoredArtifact:
        async with self._lock:
            logger.info("storage.upsert", doi=artifact.metadata.doi)
            self._memory_store[artifact.metadata.doi] = artifact
            self._persist()
        return artifact

    async def find_by_doi(self, doi: str) -> StoredArtifact | None:
        async with self._lock:
            logger.debug("storage.lookup", doi=doi)
            return self._memory_store.get(doi)

    async def list_artifacts(self) -> list[StoredArtifact]:
        async with self._lock:
            return list(self._memory_store.values())

    @property
    def root(self) -> Path:
        return self._settings.data_dir

    def pdf_path_for(self, doi: str) -> Path:
        slug = slugify(doi)
        return self._pdf_dir / f"{slug}.pdf"

    def _load_from_disk(self) -> None:
        if not self._index_path.exists():
            return
        try:
            payload = json.loads(self._index_path.read_text())
        except json.JSONDecodeError as exc:
            logger.warning("storage.load_failed", error=str(exc))
            return
        for item in payload:
            artifact = StoredArtifact.model_validate(item)
            self._memory_store[artifact.metadata.doi] = artifact

    def _persist(self) -> None:
        serialized = [
            artifact.model_dump(mode="json") for artifact in self._memory_store.values()
        ]
        self._index_path.write_text(json.dumps(serialized, indent=2))
