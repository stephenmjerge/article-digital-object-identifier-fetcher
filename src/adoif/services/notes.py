"""Services for storing per-DOI notes and reflections."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from adoif.db import NoteRecord, get_engine
from adoif.settings import Settings


@dataclass(slots=True)
class Note:
    id: int
    doi: str
    body: str
    tags: list[str]
    created_at: datetime


class NoteService:
    def __init__(self, settings: Settings) -> None:
        self._engine = get_engine(str(settings.db_path))

    def add_note(self, *, doi: str, body: str, tags: list[str] | None = None) -> Note:
        payload = NoteRecord(
            doi=doi,
            body=body,
            tags_json=json.dumps(sorted(set(tags or []))),
        )
        with Session(self._engine, expire_on_commit=False) as session:
            session.add(payload)
            session.commit()
            session.refresh(payload)
        return self._record_to_note(payload)

    def list_notes(self, doi: Optional[str] = None, limit: int = 50) -> list[Note]:
        stmt = select(NoteRecord).order_by(NoteRecord.created_at.desc()).limit(limit)
        if doi:
            stmt = stmt.where(NoteRecord.doi == doi)
        with Session(self._engine, expire_on_commit=False) as session:
            records = session.exec(stmt).all()
        return [self._record_to_note(record) for record in records]

    def _record_to_note(self, record: NoteRecord) -> Note:
        tags = json.loads(record.tags_json or "[]")
        return Note(
            id=record.id,
            doi=record.doi,
            body=record.body,
            tags=tags,
            created_at=record.created_at,
        )
