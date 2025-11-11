# Article DOI Fetcher (ADOIF)

ADOIF is a local-first research assistant that keeps decades of medical literature organized. It resolves DOIs and keywords into rich metadata, downloads open-access PDFs, extracts and enriches content, and indexes everything for fast recall during undergrad, medical school, and residency.

## Why it matters
- **Continuity of evidence** – build a longitudinal library that follows you from pre-med through fellowship.
- **Time savings** – one command ingests syllabi, PubMed alerts, or journal club packets.
- **Credibility** – reproducible logs, provenance tracking, and privacy-respecting storage highlight disciplined research habits for admissions committees.

## Guiding goals
1. Local-first with optional cloud sync so notes stay private.
2. Deterministic storage layout + metadata DB for easy backup.
3. Open-access-first fetching with clear fallbacks.
4. Rich search (full text + tags + semantic vectors).
5. Automation hooks (auto-tagging, summarization cards, spaced repetition exports).

## Architecture (current + planned)
_Steps marked as planned are on the near-term roadmap and not yet implemented._
```
CLI / FastAPI endpoints
        │
Task Orchestrator (Typer/RQ workers)
        │
Resolvers ─ DOI.org / Crossref / PubMed / Unpaywall
        │
PDF Fetchers ─ OA provider → cache → storage
        │
Pipeline
  - metadata normalization (Pydantic)
  - PDF text extraction (PyMuPDF) *(planned)*
  - enrichment (MeSH tags via scispaCy, vector embedding) *(planned)*
        │
Storage Layer
  - SQLite (FTS5 + vector table *(planned)*)
  - Library filesystem layout
  - Audit logs
```

## Tech stack
- **Language**: Python 3.12
- **Tooling**: `uv` (dependency/runtime), `ruff`, `black`, `mypy`, `pytest`
- **Interfaces**: `Typer` CLI, `FastAPI` + `HTMX` mini dashboard
- **HTTP & resilience**: `httpx`, `tenacity`
- **Metadata/storage**: `pydantic`, SQLite/SQLModel + FTS5
- **Parsing (planned)**: `PyMuPDF` (fitz), `pdfminer.six`
- **Semantic search (planned)**: `chromadb`/`llama-index`
- **Background jobs (planned)**: lightweight queue with `arq` or `rq`

### Environment
| Variable | Purpose |
| --- | --- |
| `ADOIF_DATA_DIR` | Optional override for the library root (default `~/adoif-library`) |
| `ADOIF_UNPAYWALL_EMAIL` | Required for the PDF downloader (Unpaywall rate-limits via email) |

## Key workflows
| Workflow | Description |
| --- | --- |
| `adoif add <doi|query>` | Resolve metadata, fetch PDF, and persist with SHA256-tracked PDFs |
| `adoif add-batch path/to/course-pack` | Scan a folder of PDFs, derive titles, and ingest them with course tags |
| `adoif list --tag psych --missing-pdf` | Inspect the local library with filters |
| `adoif find "<query>" --sources pubmed,openalex` | Query external APIs for new literature |
| `adoif search "<query>"` | Full-text search powered by SQLite FTS5 |
| `adoif config --json` | Print resolved settings as machine-readable JSON (for scripts/tests) |
| `adoif screen start --query …` | Seed PRISMA-style screening projects with include/exclude tracking |
| `adoif extract record --doi …` | Capture PICO data and outcome measures for included studies |
| `adoif note add --doi …` | Log reflections/highlights tied to each document |
| `adoif schedule import syllabus.csv --course PSY305` | Import due dates from a course syllabus |
| `adoif schedule today --days 7` | Show what readings are due in the next few days |
| `adoif demo-report --output report.md` | Generate an admissions-ready Markdown recap |
| `adoif serve` | Launch the FastAPI dashboard (library + insights + screening + extraction) |
| `adoif export --format bibtex --tag psych` | Instant citations for papers and notes |
| `adoif verify --all` | Flag retracted/updated DOIs using Crossref relation data |
| `adoif serve` dashboard | HTMX UI for triage queue, tagging, notes |

## Quickstart demo
Need a fast way to showcase ADOIF to classmates or admissions reviewers? Follow `docs/QUICKSTART.md` for a guided walkthrough that:

- boots a clean demo library under `.adoif-data`
- ingests an article using the bundled PDF (`demo-assets/sample-article.pdf`) via `adoif add ... --pdf`
- ingests entire syllabus folders with `adoif add-batch ./course-packs/psy305 --course PSY305`
- captures reflections with `adoif note add --doi <doi> --text "Weekly discussion takeaways"`
- imports weekly reading plans with `adoif schedule import data/syllabus.csv --course PSY305`
- exports an admissions-ready summary with `adoif demo-report --output portfolio.md`
- exercises listing, search, export, verification, screening, and extraction commands
- ends with the FastAPI dashboard so you can screen-share the whole flow

Because `adoif add` now accepts `--pdf /path/to/local.pdf`, you can attach syllabi or lecture PDFs even when Unpaywall access is unavailable—perfect for offline demos.

## Roadmap
1. **Evidence notebooks & highlights**: capture reflections/notes per DOI from the CLI/dashboard.
2. **Admissions-ready report**: generate a Markdown/HTML portfolio summarizing ingest history, screening stats, and extraction progress.
3. **Syllabus scheduler**: import due dates from course materials and surface “read today” queues.
4. **Insights & study aids**: summary cards, spaced-repetition or flashcard exports.
5. **Integrations**: Notion/Zotero export plus optional cloud backup template.

## Next
1. Implement the note/highlight workflow and expose it in the dashboard.
2. Add a `adoif schedule` helper that ingests syllabus CSV/ICS files into reminders.
3. Expand automated tests to cover the new batch ingest command end-to-end.
4. Capture screenshots + demo data for the admissions portfolio bundle.

## Dashboard preview
Run `adoif serve` and visit `http://127.0.0.1:8000` for:
- **Library** – quick glance at the ingest queue, tagged items, and PDF coverage.
- **Insights** – interactive charts showing tag coverage, screening velocity, and extraction status.
- **Screening** – PRISMA counters plus inline include/exclude forms with filters.
- **Extraction** – read-only PICO cards with recorded outcomes.
