"""Services for PICO-style data extraction."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from adoif.db import ExtractionRecord, OutcomeRecord, get_engine
from adoif.settings import Settings


class ExtractionService:
    def __init__(self, settings: Settings) -> None:
        self._engine = get_engine(str(settings.db_path))

    def upsert_record(
        self,
        *,
        doi: str,
        population: str | None,
        intervention: str | None,
        comparator: str | None,
        outcomes_summary: str | None,
        notes: str | None,
        status: str,
    ) -> ExtractionRecord:
        with Session(self._engine, expire_on_commit=False) as session:
            stmt = select(ExtractionRecord).where(ExtractionRecord.doi == doi)
            record = session.exec(stmt).first()
            if record is None:
                record = ExtractionRecord(doi=doi)
            record.population = population
            record.intervention = intervention
            record.comparator = comparator
            record.outcomes_summary = outcomes_summary
            record.notes = notes
            record.status = status
            record.updated_at = datetime.utcnow()
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def list_records(self, doi: Optional[str] = None) -> list[ExtractionRecord]:
        with Session(self._engine, expire_on_commit=False) as session:
            stmt = select(ExtractionRecord)
            if doi:
                stmt = stmt.where(ExtractionRecord.doi == doi)
            stmt = stmt.order_by(ExtractionRecord.updated_at.desc())
            return session.exec(stmt).all()

    def add_outcome(
        self,
        *,
        extraction_id: int,
        description: str,
        effect_size: float | None,
        effect_unit: str | None,
        ci_low: float | None,
        ci_high: float | None,
        p_value: float | None,
    ) -> OutcomeRecord:
        with Session(self._engine, expire_on_commit=False) as session:
            outcome = OutcomeRecord(
                extraction_id=extraction_id,
                description=description,
                effect_size=effect_size,
                effect_unit=effect_unit,
                ci_low=ci_low,
                ci_high=ci_high,
                p_value=p_value,
            )
            session.add(outcome)
            session.commit()
            session.refresh(outcome)
            return outcome

    def outcomes_for(self, extraction_id: int) -> list[OutcomeRecord]:
        with Session(self._engine, expire_on_commit=False) as session:
            stmt = select(OutcomeRecord).where(OutcomeRecord.extraction_id == extraction_id)
            return session.exec(stmt).all()
