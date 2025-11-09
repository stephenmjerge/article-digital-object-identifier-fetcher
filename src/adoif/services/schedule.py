"""Services that manage syllabus-derived reading schedules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from sqlmodel import Session, select

from adoif.db import ScheduleRecord, get_engine
from adoif.settings import Settings


@dataclass(slots=True)
class ScheduleEntry:
    id: int
    course: str
    title: str
    doi: str | None
    due_date: datetime


@dataclass(slots=True)
class NewScheduleItem:
    title: str
    due_date: datetime
    doi: str | None = None


class ScheduleService:
    def __init__(self, settings: Settings) -> None:
        self._engine = get_engine(str(settings.db_path))

    def add_items(self, course: str, items: Iterable[NewScheduleItem]) -> int:
        items = list(items)
        if not items:
            return 0
        with Session(self._engine, expire_on_commit=False) as session:
            for item in items:
                record = ScheduleRecord(
                    course=course,
                    title=item.title,
                    doi=item.doi,
                    due_date=item.due_date,
                )
                session.add(record)
            session.commit()
        return len(items)

    def due_between(
        self,
        start: date,
        end: date,
        *,
        course: Optional[str] = None,
        limit: int = 50,
    ) -> list[ScheduleEntry]:
        start_dt = datetime.combine(start, datetime.min.time())
        end_dt = datetime.combine(end, datetime.max.time())
        stmt = (
            select(ScheduleRecord)
            .where(ScheduleRecord.due_date.between(start_dt, end_dt))
            .order_by(ScheduleRecord.due_date.asc())
            .limit(limit)
        )
        if course:
            stmt = stmt.where(ScheduleRecord.course == course)
        with Session(self._engine, expire_on_commit=False) as session:
            records = session.exec(stmt).all()
        return [self._record_to_entry(record) for record in records]

    def upcoming_week(self, *, course: Optional[str] = None) -> list[ScheduleEntry]:
        today = date.today()
        return self.due_between(today, today + timedelta(days=7), course=course)

    def _record_to_entry(self, record: ScheduleRecord) -> ScheduleEntry:
        return ScheduleEntry(
            id=record.id,
            course=record.course,
            title=record.title,
            doi=record.doi,
            due_date=record.due_date,
        )
