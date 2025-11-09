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

## Planned architecture
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
  - PDF text extraction (PyMuPDF)
  - enrichment (MeSH tags via scispaCy, vector embedding)
        │
Storage Layer
  - SQLite (FTS5 + vector table)
  - Library filesystem layout
  - Audit logs
```

## Tech stack
- **Language**: Python 3.12
- **Tooling**: `uv` (dependency/runtime), `ruff`, `black`, `mypy`, `pytest`
- **Interfaces**: `Typer` CLI, `FastAPI` + `HTMX` mini dashboard
- **HTTP & resilience**: `httpx`, `tenacity`
- **Parsing**: `PyMuPDF` (fitz), `pdfminer.six` fallback
- **Metadata**: `pydantic`, SQLite/SQLModel + FTS5, optional `chromadb`/`llama-index` later
- **Background jobs**: lightweight queue with `arq` or `rq`

### Environment
| Variable | Purpose |
| --- | --- |
| `ADOIF_DATA_DIR` | Optional override for the library root (default `~/adoif-library`) |
| `ADOIF_UNPAYWALL_EMAIL` | Required for the PDF downloader (Unpaywall rate-limits via email) |

## Key workflows
| Workflow | Description |
| --- | --- |
| `adoif add <doi|query>` | Resolve metadata, fetch PDF, and persist with SHA256-tracked PDFs |
| `adoif list --tag psych --missing-pdf` | Inspect the local library with filters |
| `adoif find "<query>" --sources pubmed,openalex` | Query external APIs for new literature |
| `adoif search "<query>"` | Full-text search powered by SQLite FTS5 |
| `adoif export --format bibtex --tag psych` | Instant citations for papers and notes |
| `adoif verify --all` | Flag retracted/updated DOIs using Crossref relation data |
| Dashboard (planned) | HTMX UI for triage queue, tagging, notes |

## Roadmap
1. **MVP ingest loop**: DOI resolver → metadata schema → storage API → CLI.
2. **PDF pipeline**: OA fetch, hashing, text extraction, duplicate detection.
3. **Search & tagging**: FTS indices, auto-tagging via scispaCy/MeSH, filters.
4. **Insights & study aids**: summary cards, spaced repetition exporter.
5. **Integrations**: Notion export, Zotero sync, optional cloud backup template.

## Next
1. Initialize repo tooling (`uv init`, CI, pre-commit).
2. Flesh out metadata models + storage interfaces.
3. Build CLI skeleton with dependency injection for resolvers and storage.
4. Stub FastAPI service for future dashboard.
