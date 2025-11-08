"""Storage interfaces for the local research library."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq
import structlog

from adoif.models import StoredArtifact
from adoif.settings import Settings
from adoif.utils import sha256_file, slugify

logger = structlog.get_logger(__name__)


@dataclass
class ManifestEntry:
    checksum: str
    doi: str
    path: str
    source: str | None
    license: str | None
    ingested_at: datetime


class LibraryStorage(Protocol):
    """High-level contract for persisting artifacts."""

    async def upsert(self, artifact: StoredArtifact) -> StoredArtifact:
        ...

    async def find_by_doi(self, doi: str) -> StoredArtifact | None:
        ...

    async def list_artifacts(self) -> list[StoredArtifact]:
        ...

    def temp_pdf_path(self, identifier: str) -> Path:
        ...

    async def register_pdf(
        self,
        *,
        doi: str,
        temp_path: Path,
        source: str | None,
        license: str | None,
    ) -> tuple[Path, str]:
        ...


class LocalLibrary(LibraryStorage):
    """Minimal placeholder implementation that simulates persistence."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = asyncio.Lock()
        self._memory_store: dict[str, StoredArtifact] = {}
        self._index_path = self._settings.data_dir / "library-index.json"
        self._temp_dir = self._settings.data_dir / "tmp"
        self._content_dir = self._settings.data_dir / "pdfs"
        self._manifest_path = self._settings.data_dir / "manifest.parquet"
        self._settings.ensure_directories()
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        self._content_dir.mkdir(parents=True, exist_ok=True)
        self._manifest: dict[str, ManifestEntry] = {}
        self._load_from_disk()
        self._load_manifest()

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

    def temp_pdf_path(self, identifier: str) -> Path:
        slug = slugify(identifier)
        filename = f"{slug}-{uuid4().hex}.pdf"
        return self._temp_dir / filename

    async def register_pdf(
        self,
        *,
        doi: str,
        temp_path: Path,
        source: str | None,
        license: str | None,
    ) -> tuple[Path, str]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._register_pdf_sync, doi, temp_path, source, license
        )

    def _register_pdf_sync(
        self, doi: str, temp_path: Path, source: str | None, license: str | None
    ) -> tuple[Path, str]:
        checksum = sha256_file(temp_path)
        directory = self._content_dir / checksum[:2]
        directory.mkdir(parents=True, exist_ok=True)
        final_path = directory / f"{checksum}.pdf"
        if final_path.exists():
            temp_path.unlink(missing_ok=True)
        else:
            temp_path.replace(final_path)
        entry = ManifestEntry(
            checksum=checksum,
            doi=doi,
            path=str(final_path),
            source=source,
            license=license,
            ingested_at=datetime.utcnow(),
        )
        self._manifest[checksum] = entry
        self._persist_manifest()
        return final_path, checksum

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

    def _load_manifest(self) -> None:
        if not self._manifest_path.exists():
            return
        try:
            table = pq.read_table(self._manifest_path)
        except Exception as exc:  # pragma: no cover - corrupted file edge case
            logger.warning("storage.manifest_load_failed", error=str(exc))
            return
        for row in table.to_pylist():
            entry = ManifestEntry(
                checksum=row["checksum"],
                doi=row["doi"],
                path=row["path"],
                source=row.get("source"),
                license=row.get("license"),
                ingested_at=datetime.fromisoformat(row["ingested_at"]),
            )
            self._manifest[entry.checksum] = entry

    def _persist(self) -> None:
        serialized = [
            artifact.model_dump(mode="json") for artifact in self._memory_store.values()
        ]
        self._index_path.write_text(json.dumps(serialized, indent=2))

    def _persist_manifest(self) -> None:
        if not self._manifest:
            return
        table = pa.Table.from_pylist(
            [
                {
                    **asdict(entry),
                    "ingested_at": entry.ingested_at.isoformat(),
                }
                for entry in self._manifest.values()
            ]
        )
        pq.write_table(table, self._manifest_path)
