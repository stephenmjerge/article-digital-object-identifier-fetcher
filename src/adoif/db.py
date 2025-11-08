"""SQLite persistence layer for ADOIF."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

from sqlmodel import Field, Session, SQLModel, create_engine, select


class ArtifactRecord(SQLModel, table=True):
    """Normalized artifact row."""

    doi: str = Field(primary_key=True)
    title: str
    journal: str | None = None
    abstract: str | None = None
    publication_date: datetime | None = None
    url: str | None = None
    authors_json: str = Field(default="[]")
    tags_json: str = Field(default="[]")
    source_payload: str = Field(default="{}")
    stored_at: datetime = Field(default_factory=datetime.utcnow)
    checksum: str | None = None
    pdf_path: str | None = None
    text_path: str | None = None


class FileRecord(SQLModel, table=True):
    """Tracks deduplicated files stored locally."""

    checksum: str = Field(primary_key=True)
    doi: str
    path: str
    source: str | None = None
    license: str | None = None
    host_type: str | None = None
    ingested_at: datetime = Field(default_factory=datetime.utcnow)


def create_engine_for_path(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        connect_args={"check_same_thread": False},
    )


def init_db(engine) -> None:
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS artifact_fts
            USING fts5(doi UNINDEXED, title, abstract, tags);
            """
        )


def upsert_fts(engine, doi: str, title: str, abstract: str | None, tags: Iterable[str]) -> None:
    tag_text = " ".join(tags)
    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM artifact_fts WHERE doi = ?", (doi,))
        conn.exec_driver_sql(
            "INSERT INTO artifact_fts (doi, title, abstract, tags) VALUES (?, ?, ?, ?)",
            (doi, title, abstract or "", tag_text),
        )
