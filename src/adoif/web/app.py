"""FastAPI dashboard for ADOIF."""

from __future__ import annotations

import asyncio
from collections import Counter
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

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
    async def screening_detail(
        request: Request, project_id: int, status_filter: str = "all"
    ) -> HTMLResponse:
        service = screening()
        projects = await asyncio.to_thread(service.list_projects)
        project = next((p for p in projects if p.id == project_id), None)
        if project is None:
            return RedirectResponse("/screening", status_code=status.HTTP_302_FOUND)
        candidates = await asyncio.to_thread(service.list_candidates, project_id, status_filter)
        summary = await asyncio.to_thread(service.prisma_summary, project_id)
        return templates.TemplateResponse(
            request,
            "screening_detail.html",
            {
                "project": project,
                "candidates": candidates,
                "status_filter": status_filter,
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

    @app.get("/insights", response_class=HTMLResponse)
    async def insights(request: Request) -> HTMLResponse:
        storage = library()
        artifacts = await storage.list_artifacts()
        total = len(artifacts)
        pdfs = sum(1 for artifact in artifacts if artifact.pdf_path)
        tag_counter: Counter[str] = Counter()
        for artifact in artifacts:
            tag_counter.update(artifact.metadata.tags)
        top_tags = tag_counter.most_common(6) or [("No Tags", 1)]

        screen_service = screening()
        projects = await asyncio.to_thread(screen_service.list_projects)
        screening_labels = []
        included = []
        excluded = []
        pending_vals = []
        for project in projects:
            summary = await asyncio.to_thread(screen_service.prisma_summary, project.id)
            screening_labels.append(project.name)
            included.append(summary.included)
            excluded.append(summary.excluded)
            pending_vals.append(summary.pending)

        extract_service = extraction()
        records = await asyncio.to_thread(extract_service.list_records)
        status_counter = Counter(record.status for record in records) or Counter({"draft": 1})

        chart_payload = {
            "tags": {
                "labels": [tag for tag, _ in top_tags],
                "values": [count for _, count in top_tags],
                "colors": ["#1d4ed8", "#9333ea", "#14b8a6", "#f97316", "#0ea5e9", "#facc15"],
            },
            "screening": {
                "labels": screening_labels or ["No Projects"],
                "included": included or [0],
                "excluded": excluded or [0],
                "pending": pending_vals or [0],
            },
            "extractions": {
                "labels": list(status_counter.keys()),
                "values": list(status_counter.values()),
                "colors": ["#2563eb", "#10b981", "#eab308", "#f97316", "#ef4444"],
            },
        }

        totals = {
            "library": total,
            "pdfs": pdfs,
            "projects": len(projects),
            "extractions": len(records),
        }

        return templates.TemplateResponse(
            request,
            "insights.html",
            {"charts": chart_payload, "totals": totals},
        )

    return app


app = create_app()
