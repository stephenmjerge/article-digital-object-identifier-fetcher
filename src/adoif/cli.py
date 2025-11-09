"""Command-line interface for the ADOIF project."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import httpx
import structlog
import typer
from rich.console import Console
from rich.table import Table

from adoif import exporters
from adoif.models import FetchRequest, StoredArtifact
from adoif.services import (
    BatchScanner,
    CrossrefResolver,
    CrossrefVerifier,
    ExtractionService,
    IngestError,
    IngestPipeline,
    LocalLibrary,
    ManualOverrides,
    OpenAlexSearchResolver,
    PrismaSummary,
    PubMedSearchResolver,
    ResolverRegistry,
    ScreeningService,
    SearchAggregator,
    SearchResult,
    summarize_candidates,
    UnpaywallPDFFetcher,
)
from adoif.services.verification import VerificationResult
from adoif.settings import Settings, get_settings

console = Console()
app = typer.Typer(help="ADOIF – Article / DOI Fetcher")
screen_app = typer.Typer(help="Screening workflows")
extract_app = typer.Typer(help="PICO extraction workflows")
app.add_typer(screen_app, name="screen")
app.add_typer(extract_app, name="extract")
SCREEN_LABELS = {"include", "exclude", "maybe", "unreviewed"}
logger = structlog.get_logger(__name__)


async def _handle_add(
    identifier: str,
    title: Optional[str],
    journal: Optional[str],
    tags: tuple[str, ...],
    dry_run: bool,
    pdf_path: Optional[Path],
) -> None:
    settings = get_settings()
    storage = LocalLibrary(settings)
    request = FetchRequest(identifier=identifier)
    overrides = ManualOverrides(title=title, journal=journal, tags=tags)

    async with httpx.AsyncClient(timeout=30) as client:
        registry = ResolverRegistry([CrossrefResolver(client=client, settings=settings)])
        pdf_fetcher = UnpaywallPDFFetcher(client=client, settings=settings)
        pipeline = IngestPipeline(registry=registry, storage=storage, pdf_fetcher=pdf_fetcher)
        outcome = await pipeline.ingest(
            request=request,
            overrides=overrides,
            persist=not dry_run,
            local_pdf=pdf_path,
        )

    artifact = outcome.artifact

    if dry_run:
        console.print("[yellow]Dry run – not persisting metadata or PDFs.")
        _print_metadata(artifact)
        return

    action = "Stored" if outcome.created else "Updated"
    message = f"[green]{action}[/green]: {artifact.metadata.title}"
    if outcome.pdf_saved:
        detail = "attached" if pdf_path else "downloaded"
        message += f" (PDF {detail})"
    elif settings.unpaywall_email is None:
        message += " [yellow](No PDF – set ADOIF_UNPAYWALL_EMAIL)[/yellow]"
    console.print(message)


def _print_metadata(artifact: StoredArtifact) -> None:
    table = Table(title="Artifact Preview")
    table.add_column("Field")
    table.add_column("Value", overflow="fold")
    table.add_row("DOI", artifact.metadata.doi)
    table.add_row("Title", artifact.metadata.title)
    table.add_row("Journal", artifact.metadata.journal or "—")
    table.add_row(
        "Authors",
        ", ".join(author.full_name for author in artifact.metadata.authors) or "—",
    )
    table.add_row("Tags", ", ".join(artifact.metadata.tags) or "—")
    console.print(table)


@app.command()
def init(library_dir: Optional[Path] = typer.Option(None, help="Override data directory")) -> None:
    """Create the data directory and bootstrap configuration."""
    settings = get_settings()
    target = library_dir or settings.data_dir
    target.mkdir(parents=True, exist_ok=True)
    console.print(f"[green]Library ready:[/green] {target}")
    if library_dir:
        _write_env_var("ADOIF_DATA_DIR", str(target))
        console.print("Updated .env with ADOIF_DATA_DIR")


def _write_env_var(key: str, value: str) -> None:
    env_path = Path(".env")
    lines = []
    if env_path.exists():
        lines = [line for line in env_path.read_text().splitlines() if not line.startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n")


@app.command()
def config() -> None:
    """Display the resolved settings."""
    settings = get_settings()
    table = Table(title="ADOIF Settings")
    table.add_column("Key")
    table.add_column("Value", overflow="fold")
    for key, value in settings.model_dump().items():
        table.add_row(key, str(value))
    console.print(table)


@app.command()
def add(
    identifier: str = typer.Argument(..., help="DOI, PMID, or keyword query"),
    title: Optional[str] = typer.Option(None, help="Manual title override"),
    journal: Optional[str] = typer.Option(None, help="Manual journal override"),
    tag: Optional[list[str]] = typer.Option(None, "--tag", "-t", help="Tag applied to the record"),
    pdf: Optional[Path] = typer.Option(
        None,
        "--pdf",
        help="Attach an existing PDF instead of downloading via Unpaywall",
    ),
    dry_run: bool = typer.Option(False, help="Run pipeline without persistence"),
) -> None:
    """Add a new article to the research library."""

    async def runner() -> None:
        pdf_path = None
        if pdf:
            if not pdf.exists():
                raise typer.BadParameter("PDF path does not exist.")
            if not pdf.is_file():
                raise typer.BadParameter("PDF path must point to a file.")
            pdf_path = pdf
        try:
            await _handle_add(identifier, title, journal, tuple(tag or []), dry_run, pdf_path)
        except IngestError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc

    asyncio.run(runner())


@app.command("add-batch")
def add_batch(
    directory: Path = typer.Argument(..., exists=True, file_okay=False, readable=True, resolve_path=True),
    course: Optional[str] = typer.Option(None, help="Course name tag applied to every record"),
    tag: Optional[list[str]] = typer.Option(None, "--tag", "-t", help="Additional tags"),
    limit: Optional[int] = typer.Option(None, help="Maximum PDFs to process"),
    dry_run: bool = typer.Option(False, help="Preview detected metadata without ingesting"),
) -> None:
    """Ingest every PDF in a course-pack directory."""

    scanner = BatchScanner()
    candidates = scanner.scan(directory, limit=limit)
    if not candidates:
        console.print("[yellow]No PDFs found in the provided directory.")
        return

    table = Table(title=f"Batch preview ({len(candidates)} PDFs)")
    table.add_column("File")
    table.add_column("Title")
    table.add_column("DOI")
    for candidate in candidates:
        table.add_row(candidate.path.name, candidate.title, candidate.doi or "—")
    console.print(table)

    tags: list[str] = list(tag or [])
    if course:
        tags.append(course)
    tags = sorted(set(tags))

    if dry_run:
        console.print("[yellow]Dry run – no records were ingested.")
        return

    async def runner() -> None:
        settings = get_settings()
        storage = LocalLibrary(settings)
        async with httpx.AsyncClient(timeout=30) as client:
            registry = ResolverRegistry([CrossrefResolver(client=client, settings=settings)])
            pipeline = IngestPipeline(
                registry=registry,
                storage=storage,
                pdf_fetcher=UnpaywallPDFFetcher(client=client, settings=settings),
            )
            for candidate in candidates:
                identifier = candidate.doi or candidate.identifier
                overrides = ManualOverrides(title=candidate.title, tags=tuple(tags))
                try:
                    outcome = await pipeline.ingest(
                        request=FetchRequest(identifier=identifier),
                        overrides=overrides,
                        local_pdf=candidate.path,
                    )
                except IngestError as exc:
                    console.print(
                        f"[red]{candidate.path.name}: failed[/red] – {exc}"
                    )
                    continue
                action = "Stored" if outcome.created else "Updated"
                console.print(
                    f"[green]{candidate.path.name}[/green]: {action} • {candidate.title}"
                )

    asyncio.run(runner())


@app.command("list")
def list_items(
    tag: Optional[str] = typer.Option(None, help="Filter by tag"),
    missing_pdf: bool = typer.Option(False, help="Only show entries without a PDF"),
) -> None:
    """List stored artifacts."""

    async def runner() -> None:
        settings = get_settings()
        storage = LocalLibrary(settings)
        items = await storage.list_artifacts()
        if tag:
            items = [artifact for artifact in items if tag in artifact.metadata.tags]
        if missing_pdf:
            items = [artifact for artifact in items if not artifact.pdf_path]
        if not items:
            console.print("[yellow]Library is empty. Use `adoif add` to ingest content.")
            return
        table = Table(title="Stored Artifacts")
        table.add_column("DOI")
        table.add_column("Title")
        table.add_column("Journal")
        table.add_column("Tags")
        table.add_column("PDF")
        for artifact in items:
            table.add_row(
                artifact.metadata.doi,
                artifact.metadata.title,
                artifact.metadata.journal or "—",
                ", ".join(artifact.metadata.tags) or "—",
                "Yes" if artifact.pdf_path else "No",
            )
        console.print(table)

    asyncio.run(runner())


@app.command()
def export(
    format: str = typer.Option("bibtex", help="Export format", case_sensitive=False),
    tag: Optional[str] = typer.Option(None, help="Filter by tag"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write to file"),
) -> None:
    """Export citations as BibTeX or CSL JSON."""

    fmt = format.lower()
    if fmt not in {"bibtex", "csljson"}:
        raise typer.BadParameter("Format must be 'bibtex' or 'csljson'.")

    async def runner() -> None:
        settings = get_settings()
        storage = LocalLibrary(settings)
        items = await storage.list_artifacts()
        if tag:
            items = [artifact for artifact in items if tag in artifact.metadata.tags]
        if not items:
            console.print("[yellow]No artifacts matched the export criteria.")
            return
        payload = (
            exporters.export_bibtex(items)
            if fmt == "bibtex"
            else exporters.export_csl_json(items)
        )
        if output:
            output.write_text(payload)
            console.print(f"[green]Wrote {fmt} export to {output}")
        else:
            console.print(payload)

    asyncio.run(runner())


@app.command()
def verify(
    doi: Optional[str] = typer.Option(None, help="Single DOI to verify"),
    all: bool = typer.Option(False, "--all", help="Verify every stored artifact"),
) -> None:
    """Check Crossref for retractions or updates."""

    if not doi and not all:
        raise typer.BadParameter("Provide a DOI or use --all.")

    async def runner() -> None:
        settings = get_settings()
        storage = LocalLibrary(settings)
        targets: list[str] = []
        if all:
            items = await storage.list_artifacts()
            targets.extend([artifact.metadata.doi for artifact in items if artifact.metadata.doi])
        if doi:
            targets.append(doi)
        if not targets:
            console.print("[yellow]No DOIs available to verify.")
            return
        async with httpx.AsyncClient(timeout=20) as client:
            verifier = CrossrefVerifier(client, settings)
            results = await verifier.verify_many(targets)
        _render_verification_table(results)

    asyncio.run(runner())


def _render_verification_table(results: list[VerificationResult]) -> None:
    table = Table(title="Verification Results")
    table.add_column("DOI")
    table.add_column("Status")
    table.add_column("Notes")
    for result in results:
        notes = "; ".join(result.notes) if result.notes else "—"
        status_color = {
            "retracted": "red",
            "updated": "yellow",
            "corrected": "yellow",
            "replaced": "yellow",
            "error": "red",
        }.get(result.status, "green")
        table.add_row(result.doi, f"[{status_color}]{result.status}[/{status_color}]", notes)
    console.print(table)


@app.command()
def search(
    query: str = typer.Argument(..., help="FTS query string"),
    limit: int = typer.Option(25, help="Maximum number of results"),
) -> None:
    """Full-text search across stored artifacts."""

    async def runner() -> None:
        settings = get_settings()
        storage = LocalLibrary(settings)
        items = await storage.search(query, limit)
        if not items:
            console.print("[yellow]No matches. Try another query.")
            return
        _print_search_results(items)

    asyncio.run(runner())


def _print_search_results(items: list[StoredArtifact]) -> None:
    table = Table(title="Search Results")
    table.add_column("DOI")
    table.add_column("Title")
    table.add_column("Journal")
    table.add_column("Tags")
    for artifact in items:
        table.add_row(
            artifact.metadata.doi,
            artifact.metadata.title,
            artifact.metadata.journal or "—",
            ", ".join(artifact.metadata.tags) or "—",
        )
    console.print(table)


def _build_search_aggregator(client: httpx.AsyncClient) -> SearchAggregator:
    return SearchAggregator(
        [PubMedSearchResolver(client), OpenAlexSearchResolver(client)]
    )


def _parse_sources(value: str) -> set[str]:
    items = {entry.strip().lower() for entry in value.split(",") if entry.strip()}
    return items or {"all"}


@app.command()
def find(
    query: str = typer.Argument(..., help="External search query"),
    sources: str = typer.Option(
        "pubmed,openalex",
        help="Comma-separated sources (pubmed, openalex, all)",
    ),
    limit: int = typer.Option(20, help="Total maximum results"),
) -> None:
    """Search external APIs (PubMed/OpenAlex) for new articles."""

    source_set = _parse_sources(sources)

    async def runner() -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            aggregator = _build_search_aggregator(client)
            results = await aggregator.search(query, sources=source_set, limit=limit)
        if not results:
            console.print("[yellow]No results returned. Try another query or source.")
            return
        _print_find_results(results)

    asyncio.run(runner())


def _print_find_results(results: list[SearchResult]) -> None:
    table = Table(title="External Search Results")
    table.add_column("Source")
    table.add_column("Title")
    table.add_column("Identifier")
    table.add_column("Journal")
    table.add_column("Year")
    for entry in results:
        table.add_row(
            entry.source,
            entry.title,
            entry.identifier or "—",
            entry.journal or "—",
            entry.year or "—",
        )
    console.print(table)


@screen_app.command("projects")
def screen_projects() -> None:
    """List screening projects."""

    service = ScreeningService(get_settings())
    projects = service.list_projects()
    if not projects:
        console.print("[yellow]No screening projects yet. Use `adoif screen start`.")
        return
    table = Table(title="Screening Projects")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Query")
    table.add_column("Sources")
    table.add_column("Created")
    for project in projects:
        table.add_row(
            str(project.id),
            project.name,
            project.query,
            project.sources,
            project.created_at.strftime("%Y-%m-%d"),
        )
    console.print(table)


@screen_app.command("start")
def screen_start(
    name: str = typer.Option(..., help="Project name"),
    query: str = typer.Option(..., help="Search query"),
    sources: str = typer.Option("pubmed,openalex", help="Comma-separated sources"),
    limit: int = typer.Option(40, help="Max results to ingest"),
    notes: Optional[str] = typer.Option(None, help="Optional notes"),
) -> None:
    """Create a new screening project and seed candidates."""

    source_set = _parse_sources(sources)

    async def runner() -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            aggregator = _build_search_aggregator(client)
            results = await aggregator.search(query, sources=source_set, limit=limit)
        if not results:
            console.print("[yellow]No results returned; project not created.")
            return
        service = ScreeningService(get_settings())
        project = service.create_project(
            name=name,
            query=query,
            sources=source_set,
            notes=notes,
            results=results,
        )
        console.print(
            f"[green]Created project {project.id}[/green] with {len(results)} candidates."
        )

    asyncio.run(runner())


@screen_app.command("candidates")
def screen_candidates(
    project_id: int = typer.Option(..., help="Project ID"),
    status: str = typer.Option("all", help="Filter by status"),
) -> None:
    service = ScreeningService(get_settings())
    items = service.list_candidates(project_id, status=status)
    if not items:
        console.print("[yellow]No candidates match the filter.")
        return
    table = Table(title=f"Candidates for project {project_id}")
    table.add_column("Candidate ID")
    table.add_column("Title")
    table.add_column("Source")
    table.add_column("Status")
    table.add_column("Reason")
    for item in items:
        table.add_row(
            str(item.id),
            item.title,
            item.source,
            item.status,
            item.reason or "—",
        )
    console.print(table)


@screen_app.command("label")
def screen_label(
    candidate_id: int = typer.Option(..., help="Candidate ID"),
    label: str = typer.Option(..., help="include/exclude/maybe"),
    reason: Optional[str] = typer.Option(None, help="Optional rationale"),
) -> None:
    label_lower = label.lower()
    if label_lower not in SCREEN_LABELS:
        raise typer.BadParameter(f"Label must be one of {', '.join(SCREEN_LABELS)}")
    service = ScreeningService(get_settings())
    updated = service.update_candidate(candidate_id, status=label_lower, reason=reason)
    if not updated:
        console.print("[red]Candidate not found.")
        raise typer.Exit(code=1)
    console.print(
        f"[green]Updated candidate {candidate_id}[/green] → {label_lower}"
    )


@screen_app.command("prisma")
def screen_prisma(project_id: int = typer.Option(..., help="Project ID")) -> None:
    service = ScreeningService(get_settings())
    summary = service.prisma_summary(project_id)
    _print_prisma_summary(summary)


def _print_prisma_summary(summary: PrismaSummary) -> None:
    table = Table(title=f"PRISMA Summary (Project {summary.project_id})")
    table.add_column("Metric")
    table.add_column("Count")
    table.add_row("Total", str(summary.total))
    table.add_row("Included", str(summary.included))
    table.add_row("Excluded", str(summary.excluded))
    table.add_row("Pending", str(summary.pending))
    console.print(table)


@extract_app.command("record")
def extract_record(
    doi: str = typer.Option(..., help="DOI to annotate"),
    population: Optional[str] = typer.Option(None, help="Population summary"),
    intervention: Optional[str] = typer.Option(None, help="Intervention"),
    comparator: Optional[str] = typer.Option(None, help="Comparator"),
    outcomes: Optional[str] = typer.Option(None, help="Outcomes summary"),
    notes: Optional[str] = typer.Option(None, help="Additional notes"),
    status: str = typer.Option("draft", help="draft|completed"),
    outcome_description: Optional[str] = typer.Option(None, help="Outcome detail"),
    effect_size: Optional[float] = typer.Option(None, help="Effect size value"),
    effect_unit: Optional[str] = typer.Option(None, help="Effect size unit"),
    ci_low: Optional[float] = typer.Option(None, help="Confidence interval low"),
    ci_high: Optional[float] = typer.Option(None, help="Confidence interval high"),
    p_value: Optional[float] = typer.Option(None, help="p-value"),
) -> None:
    """Create or update a PICO extraction record."""

    service = ExtractionService(get_settings())
    record = service.upsert_record(
        doi=doi,
        population=population,
        intervention=intervention,
        comparator=comparator,
        outcomes_summary=outcomes,
        notes=notes,
        status=status,
    )
    if outcome_description:
        service.add_outcome(
            extraction_id=record.id,
            description=outcome_description,
            effect_size=effect_size,
            effect_unit=effect_unit,
            ci_low=ci_low,
            ci_high=ci_high,
            p_value=p_value,
        )
    console.print(f"[green]Saved extraction for {doi}[/green]")


@extract_app.command("list")
def extract_list(doi: Optional[str] = typer.Option(None, help="Filter by DOI")) -> None:
    """List stored extraction records."""

    service = ExtractionService(get_settings())
    records = service.list_records(doi=doi)
    if not records:
        console.print("[yellow]No extraction records found.")
        return
    table = Table(title="Extraction Records")
    table.add_column("ID")
    table.add_column("DOI")
    table.add_column("Population")
    table.add_column("Intervention")
    table.add_column("Comparator")
    table.add_column("Status")
    for record in records:
        table.add_row(
            str(record.id),
            record.doi,
            record.population or "—",
            record.intervention or "—",
            record.comparator or "—",
            record.status,
        )
    console.print(table)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host interface"),
    port: int = typer.Option(8000, help="Port to bind"),
    reload: bool = typer.Option(False, help="Enable auto-reload"),
) -> None:
    """Launch the FastAPI dashboard."""
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover
        console.print("[red]FastAPI dependencies not installed.[/red]")
        raise typer.Exit(code=1) from exc

    uvicorn.run(
        "adoif.web.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )
