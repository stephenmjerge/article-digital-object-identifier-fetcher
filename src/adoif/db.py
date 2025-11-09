"""SQLite persistence layer for ADOIF."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
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


class ScreeningProject(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    query: str
    sources: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    notes: str | None = None


class ScreeningCandidate(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="screeningproject.id")
    identifier: str | None = None
    title: str
    journal: str | None = None
    year: str | None = None
    source: str
    url: str | None = None
    status: str = Field(default="unreviewed")
    reason: str | None = None
    metadata_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ExtractionRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    doi: str
    population: str | None = None
    intervention: str | None = None
    comparator: str | None = None
    outcomes_summary: str | None = None
    notes: str | None = None
    status: str = Field(default="draft")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class OutcomeRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    extraction_id: int = Field(foreign_key="extractionrecord.id")
    description: str
    effect_size: float | None = None
    effect_unit: str | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    p_value: float | None = None


class NoteRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    doi: str
    body: str
    tags_json: str = Field(default="[]")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ScheduleRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    course: str
    title: str
    doi: str | None = None
    due_date: datetime


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


@lru_cache(maxsize=4)
def get_engine(path_str: str):
    engine = create_engine_for_path(Path(path_str))
    init_db(engine)
    return engine


def upsert_fts(engine, doi: str, title: str, abstract: str | None, tags: Iterable[str]) -> None:
    tag_text = " ".join(tags)
    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM artifact_fts WHERE doi = ?", (doi,))
        conn.exec_driver_sql(
            "INSERT INTO artifact_fts (doi, title, abstract, tags) VALUES (?, ?, ?, ?)",
            (doi, title, abstract or "", tag_text),
        )
