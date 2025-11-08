"""Storage interfaces for the local research library backed by SQLite."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import structlog
from sqlalchemy import text
from sqlmodel import Session, select

from adoif.db import ArtifactRecord, FileRecord, create_engine_for_path, init_db, upsert_fts
from adoif.models import ArticleMetadata, Author, StoredArtifact
from adoif.settings import Settings
from adoif.utils import sha256_file, slugify

logger = structlog.get_logger(__name__)


class LibraryStorage(Protocol):
    """High-level contract for persisting artifacts."""

    async def upsert(self, artifact: StoredArtifact) -> StoredArtifact:
        ...

    async def find_by_doi(self, doi: str) -> StoredArtifact | None:
        ...

    async def list_artifacts(self) -> list[StoredArtifact]:
        ...

    async def search(self, query: str, limit: int = 25) -> list[StoredArtifact]:
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
        host_type: str | None,
    ) -> tuple[Path, str]:
        ...


class LocalLibrary(LibraryStorage):
    """SQLite-backed implementation of the research library."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = asyncio.Lock()
        self._index_path = self._settings.data_dir / "library-index.json"
        self._temp_dir = self._settings.data_dir / "tmp"
        self._content_dir = self._settings.data_dir / "pdfs"
        self._settings.ensure_directories()
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        self._content_dir.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine_for_path(self._settings.db_path)
        init_db(self._engine)
        self._bootstrap_from_legacy_index()

    async def upsert(self, artifact: StoredArtifact) -> StoredArtifact:
        async with self._lock:
            await asyncio.to_thread(self._upsert_sync, artifact)
        return artifact

    async def find_by_doi(self, doi: str) -> StoredArtifact | None:
        async with self._lock:
            return await asyncio.to_thread(self._find_sync, doi)

    async def list_artifacts(self) -> list[StoredArtifact]:
        async with self._lock:
            return await asyncio.to_thread(self._list_sync)

    async def search(self, query: str, limit: int = 25) -> list[StoredArtifact]:
        async with self._lock:
            return await asyncio.to_thread(self._search_sync, query, limit)

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
        host_type: str | None,
    ) -> tuple[Path, str]:
        return await asyncio.to_thread(
            self._register_pdf_sync, doi, temp_path, source, license, host_type
        )

    # Internal helpers -----------------------------------------------------

    def _upsert_sync(self, artifact: StoredArtifact) -> None:
        metadata = artifact.metadata
        with Session(self._engine) as session:
            record = session.get(ArtifactRecord, metadata.doi)
            if record is None:
                record = ArtifactRecord(doi=metadata.doi, stored_at=artifact.stored_at)
            record.title = metadata.title
            record.journal = metadata.journal
            record.abstract = metadata.abstract
            record.publication_date = metadata.publication_date
            record.url = metadata.url
            record.authors_json = json.dumps([author.model_dump() for author in metadata.authors])
            record.tags_json = json.dumps(metadata.tags)
            record.source_payload = json.dumps(metadata.source_payload)
            record.stored_at = artifact.stored_at
            record.checksum = artifact.checksum
            record.pdf_path = str(artifact.pdf_path) if artifact.pdf_path else None
            record.text_path = str(artifact.text_path) if artifact.text_path else None
            session.add(record)
            session.commit()
        upsert_fts(
            self._engine,
            doi=metadata.doi,
            title=metadata.title,
            abstract=metadata.abstract,
            tags=metadata.tags,
        )

    def _find_sync(self, doi: str) -> StoredArtifact | None:
        with Session(self._engine) as session:
            record = session.get(ArtifactRecord, doi)
            return self._record_to_artifact(record) if record else None

    def _list_sync(self) -> list[StoredArtifact]:
        with Session(self._engine) as session:
            statement = select(ArtifactRecord).order_by(ArtifactRecord.stored_at.desc())
            records = session.exec(statement).all()
        return [self._record_to_artifact(record) for record in records]

    def _search_sync(self, query: str, limit: int) -> list[StoredArtifact]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT doi FROM artifact_fts WHERE artifact_fts MATCH :query LIMIT :limit"
                ),
                {"query": query, "limit": limit},
            ).fetchall()
        dois = [row[0] for row in rows]
        if not dois:
            return []
        with Session(self._engine) as session:
            statement = select(ArtifactRecord).where(ArtifactRecord.doi.in_(dois))
            records = session.exec(statement).all()
        record_map = {record.doi: record for record in records}
        ordered = [record_map[doi] for doi in dois if doi in record_map]
        return [self._record_to_artifact(record) for record in ordered]

    def _register_pdf_sync(
        self,
        doi: str,
        temp_path: Path,
        source: str | None,
        license: str | None,
        host_type: str | None,
    ) -> tuple[Path, str]:
        checksum = sha256_file(temp_path)
        directory = self._content_dir / checksum[:2]
        directory.mkdir(parents=True, exist_ok=True)
        final_path = directory / f"{checksum}.pdf"
        if final_path.exists():
            temp_path.unlink(missing_ok=True)
        else:
            temp_path.replace(final_path)

        with Session(self._engine) as session:
            record = session.get(FileRecord, checksum)
            if record is None:
                record = FileRecord(checksum=checksum, doi=doi, path=str(final_path))
            record.doi = doi
            record.path = str(final_path)
            record.source = source
            record.license = license
            record.host_type = host_type
            record.ingested_at = datetime.utcnow()
            session.add(record)
            session.commit()

        return final_path, checksum

    def _record_to_artifact(self, record: ArtifactRecord) -> StoredArtifact:
        authors_payload = json.loads(record.authors_json or "[]")
        tags_payload = json.loads(record.tags_json or "[]")
        metadata = ArticleMetadata(
            doi=record.doi,
            title=record.title,
            authors=[Author.model_validate(author) for author in authors_payload],
            journal=record.journal,
            abstract=record.abstract,
            publication_date=record.publication_date,
            url=record.url,
            tags=tags_payload,
            source_payload=json.loads(record.source_payload or "{}"),
        )
        return StoredArtifact(
            metadata=metadata,
            pdf_path=Path(record.pdf_path) if record.pdf_path else None,
            text_path=Path(record.text_path) if record.text_path else None,
            checksum=record.checksum,
            stored_at=record.stored_at,
        )

    def _bootstrap_from_legacy_index(self) -> None:
        if not self._index_path.exists():
            return
        try:
            payload = json.loads(self._index_path.read_text())
        except json.JSONDecodeError as exc:  # pragma: no cover - legacy file corrupted
            logger.warning("storage.legacy_load_failed", error=str(exc))
            return
        logger.info("storage.legacy_import", items=len(payload))
        for item in payload:
            artifact = StoredArtifact.model_validate(item)
            self._upsert_sync(artifact)
