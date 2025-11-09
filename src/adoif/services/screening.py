"""Screening workflows for PRISMA-style reviews."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from sqlmodel import Session, select

from adoif.db import ScreeningCandidate, ScreeningProject, get_engine
from adoif.services.search import SearchResult
from adoif.settings import Settings


@dataclass(slots=True)
class PrismaSummary:
    project_id: int
    total: int
    included: int
    excluded: int
    pending: int


class ScreeningService:
    def __init__(self, settings: Settings) -> None:
        self._engine = get_engine(str(settings.db_path))

    def create_project(
        self,
        *,
        name: str,
        query: str,
        sources: set[str],
        notes: str | None,
        results: Iterable[SearchResult],
    ) -> ScreeningProject:
        with Session(self._engine, expire_on_commit=False) as session:
            project = ScreeningProject(name=name, query=query, sources=",".join(sorted(sources)), notes=notes)
            session.add(project)
            session.commit()
            session.refresh(project)
            for result in results:
                candidate = ScreeningCandidate(
                    project_id=project.id,
                    identifier=result.identifier,
                    title=result.title,
                    journal=result.journal,
                    year=result.year,
                    source=result.source,
                    url=result.url,
                )
                session.add(candidate)
            session.commit()
            return project

    def list_projects(self) -> list[ScreeningProject]:
        with Session(self._engine, expire_on_commit=False) as session:
            stmt = select(ScreeningProject).order_by(ScreeningProject.created_at.desc())
            return session.exec(stmt).all()

    def list_candidates(self, project_id: int, status: str | None = None) -> list[ScreeningCandidate]:
        with Session(self._engine, expire_on_commit=False) as session:
            stmt = select(ScreeningCandidate).where(ScreeningCandidate.project_id == project_id)
            if status and status != "all":
                stmt = stmt.where(ScreeningCandidate.status == status)
            stmt = stmt.order_by(ScreeningCandidate.created_at.asc())
            return session.exec(stmt).all()

    def update_candidate(self, candidate_id: int, *, status: str, reason: str | None) -> ScreeningCandidate | None:
        with Session(self._engine, expire_on_commit=False) as session:
            candidate = session.get(ScreeningCandidate, candidate_id)
            if not candidate:
                return None
            candidate.status = status
            candidate.reason = reason
            candidate.updated_at = datetime.utcnow()
            session.add(candidate)
            session.commit()
            session.refresh(candidate)
            return candidate

    def prisma_summary(self, project_id: int) -> PrismaSummary:
        with Session(self._engine) as session:
            stmt = select(ScreeningCandidate.status)
            stmt = stmt.where(ScreeningCandidate.project_id == project_id)
            statuses = session.exec(stmt).all()
        total = len(statuses)
        included = sum(1 for status in statuses if status == "include")
        excluded = sum(1 for status in statuses if status == "exclude")
        pending = total - included - excluded
        return PrismaSummary(project_id=project_id, total=total, included=included, excluded=excluded, pending=pending)
