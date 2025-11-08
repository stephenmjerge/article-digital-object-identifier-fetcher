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
    CrossrefResolver,
    CrossrefVerifier,
    IngestError,
    IngestPipeline,
    LocalLibrary,
    ManualOverrides,
    ResolverRegistry,
    UnpaywallPDFFetcher,
)
from adoif.services.verification import VerificationResult
from adoif.settings import Settings, get_settings

console = Console()
app = typer.Typer(help="ADOIF – Article / DOI Fetcher")
logger = structlog.get_logger(__name__)


async def _handle_add(
    identifier: str,
    title: Optional[str],
    journal: Optional[str],
    tags: tuple[str, ...],
    dry_run: bool,
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
        )

    artifact = outcome.artifact

    if dry_run:
        console.print("[yellow]Dry run – not persisting metadata or PDFs.")
        _print_metadata(artifact)
        return

    action = "Stored" if outcome.created else "Updated"
    message = f"[green]{action}[/green]: {artifact.metadata.title}"
    if outcome.pdf_downloaded:
        message += " (PDF downloaded)"
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
    dry_run: bool = typer.Option(False, help="Run pipeline without persistence"),
) -> None:
    """Add a new article to the research library."""

    async def runner() -> None:
        try:
            await _handle_add(identifier, title, journal, tuple(tag or []), dry_run)
        except IngestError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc

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
