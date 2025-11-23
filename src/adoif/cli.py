"""Command-line interface for the ADOIF project."""

from __future__ import annotations

import asyncio
import csv
import sys
from datetime import datetime, date, timedelta
import json
from pathlib import Path
from typing import Optional

import httpx
import structlog
import typer
from rich.console import Console
from rich.table import Table

from adoif import exporters
from adoif.models import FetchRequest, StoredArtifact
from adoif.reporting import ReportData, ScreeningSnapshot, build_demo_report
from adoif.services import (
    BatchScanner,
    CrossrefResolver,
    CrossrefVerifier,
    ExtractionService,
    IngestError,
    IngestPipeline,
    LocalLibrary,
    ManualOverrides,
    NoteService,
    OpenAlexSearchResolver,
    PrismaSummary,
    PubMedSearchResolver,
    ResolverRegistry,
    ScreeningService,
    ScheduleService,
    NewScheduleItem,
    SearchAggregator,
    SearchResult,
    summarize_candidates,
    UnpaywallPDFFetcher,
)
from adoif.services.verification import VerificationResult
from adoif.settings import Settings, get_settings
from adoif.utils import slugify

console = Console()
app = typer.Typer(help="ADOIF – Article / DOI Fetcher")
screen_app = typer.Typer(help="Screening workflows")
extract_app = typer.Typer(help="PICO extraction workflows")
note_app = typer.Typer(help="Notes & reflections")
schedule_app = typer.Typer(help="Reading schedules")
app.add_typer(screen_app, name="screen")
app.add_typer(extract_app, name="extract")
app.add_typer(note_app, name="note")
app.add_typer(schedule_app, name="schedule")
SCREEN_LABELS = {"include", "exclude", "maybe", "unreviewed"}
logger = structlog.get_logger(__name__)


async def _handle_add(
    identifier: str,
    title: Optional[str],
    journal: Optional[str],
    tags: tuple[str, ...],
    dry_run: bool,
    pdf_path: Optional[Path],
) -> Optional[StoredArtifact]:
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
        return artifact

    action = "Stored" if outcome.created else "Updated"
    message = f"[green]{action}[/green]: {artifact.metadata.title}"
    if outcome.pdf_saved:
        detail = "attached" if pdf_path else "downloaded"
        message += f" (PDF {detail})"
    elif settings.unpaywall_email is None:
        message += " [yellow](No PDF – set ADOIF_UNPAYWALL_EMAIL)[/yellow]"
    console.print(message)
    return artifact


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


def _write_html_report(artifact: StoredArtifact, output_path: Path) -> None:
    output_dir = output_path if output_path.suffix == "" else output_path.parent
    output_file = output_path if output_path.suffix else output_dir / "report.html"
    output_dir.mkdir(parents=True, exist_ok=True)
    html_lines = [
        "<html><head><title>ADOIF Report</title></head><body>",
        "<h1>ADOIF Artifact</h1>",
        f"<p><strong>Title:</strong> {artifact.metadata.title}</p>",
        f"<p><strong>DOI:</strong> {artifact.metadata.doi}</p>",
        f"<p><strong>Journal:</strong> {artifact.metadata.journal or '—'}</p>",
        f"<p><strong>Authors:</strong> {', '.join(a.full_name for a in artifact.metadata.authors) or '—'}</p>",
        f"<p><strong>Tags:</strong> {', '.join(artifact.metadata.tags) or '—'}</p>",
        "</body></html>",
    ]
    output_file.write_text("\n".join(html_lines), encoding="utf-8")


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
def config(
    json_output: bool = typer.Option(False, "--json", help="Output settings as JSON"),
) -> None:
    """Display the resolved settings."""
    settings = get_settings()
    if json_output:
        typer.echo(settings.model_dump_json(indent=2))
        return
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
            artifact = await _handle_add(identifier, title, journal, tuple(tag or []), dry_run, pdf_path)
        except IngestError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc
        if not dry_run and artifact:
            report_dir = Path("outputs") / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            name = slugify(identifier)
            _write_html_report(artifact, report_dir / f"{name}.html")

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


@note_app.command("add")
def note_add(
    doi: str = typer.Option(..., help="DOI to attach the note to"),
    text: str = typer.Option(..., "--text", "-t", help="Note body"),
    tag: Optional[list[str]] = typer.Option(None, "--tag", help="Optional tags"),
) -> None:
    """Record a note/reflection for an article."""

    service = NoteService(get_settings())
    note = service.add_note(doi=doi, body=text, tags=list(tag or []))
    tag_display = f" [{', '.join(note.tags)}]" if note.tags else ""
    console.print(
        f"[green]Saved note[/green] for {note.doi}{tag_display}"
    )


@note_app.command("list")
def note_list(
    doi: Optional[str] = typer.Option(None, help="Filter notes by DOI"),
    limit: int = typer.Option(25, help="Number of notes to show"),
) -> None:
    service = NoteService(get_settings())
    notes = service.list_notes(doi=doi, limit=limit)
    if not notes:
        console.print("[yellow]No notes found.")
        return
    table = Table(title="Notes")
    table.add_column("Created")
    table.add_column("DOI")
    table.add_column("Tags")
    table.add_column("Body")
    for entry in notes:
        tag_text = ", ".join(entry.tags) or "—"
        preview = (entry.body[:80] + "…") if len(entry.body) > 80 else entry.body
        table.add_row(
            entry.created_at.strftime("%Y-%m-%d"),
            entry.doi,
            tag_text,
            preview,
        )
    console.print(table)


@schedule_app.command("import")
def schedule_import(
    file: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False, readable=True),
    course: str = typer.Option(..., help="Course tag (e.g., PSY305)"),
) -> None:
    """Import readings from a syllabus CSV (title, due_date, [doi])."""

    items = _parse_schedule_csv(file)
    if not items:
        console.print("[yellow]No rows detected in the CSV.")
        return
    service = ScheduleService(get_settings())
    count = service.add_items(course, items)
    console.print(f"[green]Imported {count} readings[/green] for {course}.")


@schedule_app.command("today")
def schedule_today(
    course: Optional[str] = typer.Option(None, help="Filter by course"),
    days: int = typer.Option(0, help="Show items due within N days from today"),
) -> None:
    service = ScheduleService(get_settings())
    start = date.today()
    end = start + timedelta(days=max(days, 0))
    entries = service.due_between(start, end, course=course)
    if not entries:
        console.print("[yellow]No readings due in the selected window.")
        return
    table = Table(title="Upcoming readings")
    table.add_column("Due")
    table.add_column("Course")
    table.add_column("Title")
    table.add_column("DOI")
    for entry in entries:
        table.add_row(
            entry.due_date.strftime("%Y-%m-%d"),
            entry.course,
            entry.title,
            entry.doi or "—",
        )
    console.print(table)


@app.command("demo-report")
def demo_report(
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write report to a file"),
    note_limit: int = typer.Option(5, help="Number of notes to include"),
) -> None:
    """Generate a Markdown snapshot for admissions reviewers."""

    async def runner() -> str:
        settings = get_settings()
        storage = LocalLibrary(settings)
        artifacts = await storage.list_artifacts()

        note_service = NoteService(settings)
        notes = note_service.list_notes(limit=note_limit)

        schedule_entries = ScheduleService(settings).upcoming_week()

        extract_service = ExtractionService(settings)
        extractions = await asyncio.to_thread(extract_service.list_records)

        screen_service = ScreeningService(settings)
        projects = await asyncio.to_thread(screen_service.list_projects)
        screening_snapshots: list[ScreeningSnapshot] = []
        for project in projects:
            summary = await asyncio.to_thread(screen_service.prisma_summary, project.id)
            screening_snapshots.append(
                ScreeningSnapshot(
                    name=project.name,
                    included=summary.included,
                    excluded=summary.excluded,
                    pending=summary.pending,
                )
            )

        report_data = ReportData(
            artifacts=artifacts,
            screening=screening_snapshots,
            extractions=extractions,
            notes=notes,
            schedule=schedule_entries,
        )
        return build_demo_report(report_data)

    content = asyncio.run(runner())
    if output:
        output.write_text(content)
        console.print(f"[green]Wrote report to {output}")
    else:
        console.print(content)


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


@app.command("export-lab")
def export_lab(
    lab: str = typer.Argument(..., help="Lab identifier (e.g., lab_x)"),
    format: str = typer.Option("csv", "--format", "-f", help="csv or json", case_sensitive=False),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write to file"),
    dois_file: Optional[Path] = typer.Option(None, help="Optional newline-separated DOI list to filter"),
) -> None:
    """Export Lab-specific citations as CSV or JSON."""

    fmt = format.lower()
    if fmt not in {"csv", "json"}:
        raise typer.BadParameter("Format must be 'csv' or 'json'.")

    doi_targets: set[str] | None = None
    if dois_file:
        doi_path = dois_file.expanduser()
        if not doi_path.exists():
            raise typer.BadParameter(f"DOI list not found: {dois_file}")
        doi_targets = _load_doi_targets(doi_path)
        if not doi_targets:
            raise typer.BadParameter(f"No DOIs found in {dois_file}")

    async def runner() -> None:
        settings = get_settings()
        storage = LocalLibrary(settings)
        items = await storage.list_artifacts()
        filtered = _filter_lab_artifacts(items, lab, doi_targets)
        if not filtered:
            console.print("[yellow]No artifacts matched the Lab export criteria.")
            return
        rows = _build_lab_export_rows(filtered)
        destination = output or Path(f"lab-{lab.lower()}-export.{fmt}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "csv":
            with destination.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
        else:
            destination.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        console.print(f"[green]Wrote {len(rows)} artifacts to {destination}")

    asyncio.run(runner())


@app.command()
def doctor(
    input_csv: Optional[Path] = typer.Option(None, "--input", help="Optional input list to validate"),
) -> None:
    """Environment checks (Python, deps, data directory)."""
    checks: list[tuple[str, bool, str]] = []
    checks.append(("python>=3.11", sys.version_info >= (3, 11), sys.version))
    for mod in ("httpx", "sqlmodel", "structlog"):
        try:
            module = __import__(mod)
            ver = getattr(module, "__version__", "unknown")
            checks.append((f"{mod} import", True, ver))
        except Exception as exc:  # pragma: no cover
            checks.append((f"{mod} import", False, str(exc)))
    settings = get_settings()
    data_dir = settings.data_dir
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        test = data_dir / ".adoif_doctor"
        test.write_text("ok", encoding="utf-8")
        test.unlink()
        checks.append(("data_dir writable", True, str(data_dir)))
    except Exception as exc:  # pragma: no cover
        checks.append(("data_dir writable", False, str(exc)))
    if input_csv:
        checks.append(("input exists", input_csv.exists(), str(input_csv)))

    passed = True
    for name, ok, note in checks:
        status = "[green]OK[/green]" if ok else "[red]FAIL[/red]"
        console.print(f"{status} {name} ({note})")
        passed = passed and ok
    if not passed:
        raise typer.Exit(code=1)
    console.print("[green]Doctor checks passed.[/green]")


@app.command()
def demo(outdir: Optional[Path] = typer.Option(None, "--outdir", help="Demo output directory")) -> None:
    """Generate a small synthetic library (metadata, CSV, HTML report)."""
    base = outdir or Path("outputs") / f"adoif_demo_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}"
    base.mkdir(parents=True, exist_ok=True)
    sample = [
        {
            "doi": "10.1038/s41591-021-01627-4",
            "title": "Ketamine for treatment-resistant depression",
            "journal": "Nature Medicine",
            "authors": ["Smith, A.", "Lee, J."],
            "tags": ["psych", "ketamine"],
        },
        {
            "doi": "10.1001/jama.2019.0018",
            "title": "Digital mental health interventions",
            "journal": "JAMA",
            "authors": ["Garcia, M.", "Nguyen, P."],
            "tags": ["digital", "psych"],
        },
    ]
    csv_path = base / "metadata.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["doi", "title", "journal", "authors", "tags"])
        writer.writeheader()
        for row in sample:
            writer.writerow({
                "doi": row["doi"],
                "title": row["title"],
                "journal": row["journal"],
                "authors": "; ".join(row["authors"]),
                "tags": ", ".join(row["tags"]),
            })
    json_path = base / "metadata.json"
    json_path.write_text(json.dumps(sample, indent=2), encoding="utf-8")

    # Build a simple HTML report
    html_lines = [
        "<html><head><title>ADOIF Demo</title></head><body>",
        "<h1>ADOIF Demo Library</h1>",
        "<ul>",
    ]
    for row in sample:
        html_lines.append(
            f"<li><strong>{row['title']}</strong> ({row['journal']}) — {row['doi']} — tags: {', '.join(row['tags'])}</li>"
        )
    html_lines.append("</ul></body></html>")
    (base / "report.html").write_text("\n".join(html_lines), encoding="utf-8")

    manifest = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "count": len(sample),
        "paths": {
            "metadata_csv": str(csv_path),
            "metadata_json": str(json_path),
            "report_html": str(base / "report.html"),
        },
    }
    (base / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    console.print(f"[green]Demo complete[/green] → {base}")


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


def _load_doi_targets(path: Path) -> set[str]:
    targets: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        targets.add(value.lower())
    return targets


def _filter_lab_artifacts(
    artifacts: list[StoredArtifact], lab: str, doi_targets: set[str] | None
) -> list[StoredArtifact]:
    if doi_targets:
        return [artifact for artifact in artifacts if artifact.metadata.doi and artifact.metadata.doi.lower() in doi_targets]
    lab_tag = f"lab:{lab.lower()}"
    return [artifact for artifact in artifacts if lab_tag in artifact.metadata.tags]


def _build_lab_export_rows(artifacts: list[StoredArtifact]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for artifact in artifacts:
        metadata = artifact.metadata
        rows.append(
            {
                "doi": metadata.doi or "",
                "title": metadata.title or "",
                "journal": metadata.journal or "",
                "year": str(metadata.year) if metadata.year else "",
                "tags": ", ".join(metadata.tags) if metadata.tags else "",
                "pdf_path": str(artifact.pdf_path) if artifact.pdf_path else "",
            }
        )
    return rows


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


def _parse_schedule_csv(path: Path) -> list[NewScheduleItem]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return []
        items: list[NewScheduleItem] = []
        for idx, row in enumerate(reader, start=1):
            due_raw = (row.get("due_date") or row.get("date") or "").strip()
            if not due_raw:
                raise typer.BadParameter(
                    "Each row must include a due_date column (YYYY-MM-DD)."
                )
            due_date = _parse_due_date(due_raw)
            title = (row.get("title") or row.get("reading") or f"Reading {idx}").strip()
            doi = (row.get("doi") or row.get("identifier") or "").strip() or None
            items.append(NewScheduleItem(title=title or f"Reading {idx}", due_date=due_date, doi=doi))
        return items


def _parse_due_date(value: str) -> datetime:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise typer.BadParameter(
        f"Could not parse due date '{value}'. Use YYYY-MM-DD or MM/DD/YYYY."
    )


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
