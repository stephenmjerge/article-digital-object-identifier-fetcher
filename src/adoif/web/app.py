"""FastAPI dashboard for ADOIF."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from adoif.models import StoredArtifact
from adoif.services import (
    ExtractionService,
    LocalLibrary,
    PrismaSummary,
    ScreeningService,
)
from adoif.settings import Settings, get_settings

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """Factory used by uvicorn."""
    settings = settings or get_settings()
    app = FastAPI(title="ADOIF Dashboard")
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

    def library() -> LocalLibrary:
        return LocalLibrary(settings)

    def screening() -> ScreeningService:
        return ScreeningService(settings)

    def extraction() -> ExtractionService:
        return ExtractionService(settings)

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> HTMLResponse:
        storage = library()
        artifacts = await storage.list_artifacts()
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "artifacts": artifacts,
                "total": len(artifacts),
            },
        )

    @app.get("/screening", response_class=HTMLResponse)
    async def screening_home(request: Request) -> HTMLResponse:
        service = screening()
        projects = await asyncio.to_thread(service.list_projects)
        summaries: dict[int, PrismaSummary] = {}
        for project in projects:
            summaries[project.id] = await asyncio.to_thread(service.prisma_summary, project.id)
        return templates.TemplateResponse(
            request,
            "screening.html",
            {"projects": projects, "summaries": summaries},
        )

    @app.get("/screening/{project_id}", response_class=HTMLResponse)
    async def screening_detail(request: Request, project_id: int) -> HTMLResponse:
        service = screening()
        projects = await asyncio.to_thread(service.list_projects)
        project = next((p for p in projects if p.id == project_id), None)
        if project is None:
            return RedirectResponse("/screening", status_code=status.HTTP_302_FOUND)
        candidates = await asyncio.to_thread(service.list_candidates, project_id, "all")
        summary = await asyncio.to_thread(service.prisma_summary, project_id)
        return templates.TemplateResponse(
            request,
            "screening_detail.html",
            {
                "project": project,
                "candidates": candidates,
                "summary": summary,
            },
        )

    @app.post("/screening/{project_id}/label/{candidate_id}")
    async def screening_label(
        project_id: int,
        candidate_id: int,
        label: str = Form(...),
        reason: Optional[str] = Form(None),
    ) -> RedirectResponse:
        service = screening()
        await asyncio.to_thread(service.update_candidate, candidate_id, status=label, reason=reason)
        return RedirectResponse(
            f"/screening/{project_id}", status_code=status.HTTP_302_FOUND
        )

    @app.get("/extractions", response_class=HTMLResponse)
    async def extraction_home(request: Request) -> HTMLResponse:
        service = extraction()
        records = await asyncio.to_thread(service.list_records)
        enriched = []
        for record in records:
            outcomes = await asyncio.to_thread(service.outcomes_for, record.id)
            enriched.append((record, outcomes))
        return templates.TemplateResponse(
            request,
            "extractions.html",
            {"records": enriched},
        )

    return app


app = create_app()
