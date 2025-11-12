# Article DOI Fetcher (ADOIF)

> **Research-use only:** ADOIF is a lab-grade literature assistant. Keep it for syllabi, journal clubs, and admissions portfolios—not for clinical decision making or PHI storage unless your workflow is IRB-approved and audited.

ADOIF is a local-first research assistant that keeps longitudinal clinical-research libraries organized. It resolves DOIs and keywords into rich metadata, downloads open-access PDFs, extracts and enriches content, and indexes everything for fast recall during lab rotations, practicum work, and translational collaborations.

### Visual snapshot

Record a short capture of `adoif add`, `adoif demo-report`, and the `adoif serve` dashboard, then store it under `docs/` for portfolio use (e.g., `docs/adoif-demo.gif`).

## Why it matters
- **Continuity of evidence** – build a longitudinal library that follows trainees across lab assignments, externships, and applied research rotations.
- **Time savings** – one command ingests syllabi, PubMed alerts, or journal club packets into the same reproducible structure.
- **Credibility** – reproducible logs, provenance tracking, and privacy-respecting storage highlight disciplined research habits when sharing work with supervisors or admissions committees.

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

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Environment variables

| Variable | Purpose | Example |
| --- | --- | --- |
| `ADOIF_DATA_DIR` | Override the library root (defaults to `~/adoif-library`) | `export ADOIF_DATA_DIR=$PWD/.adoif-data` |
| `ADOIF_UNPAYWALL_EMAIL` | Required by Unpaywall for polite PDF fetching | `export ADOIF_UNPAYWALL_EMAIL=you@example.edu` |
| `ADOIF_DB_FILENAME` *(optional)* | Change the SQLite filename | `export ADOIF_DB_FILENAME=library.sqlite3` |

### Smoke test

```bash
adoif init --library-dir .adoif-demo
adoif add 10.1038/s41591-021-01627-4 --tag psych --dry-run
adoif config --json
```

Use `python -m adoif.cli ...` if the console entry point is unavailable.

## CLI cheatsheet

| Command | Purpose | Example |
| --- | --- | --- |
| `adoif add <doi|query>` | Resolve metadata, fetch/attach PDFs, persist to library | `adoif add 10.1038/s41591-021-01627-4 --tag psych --pdf demo-assets/sample-article.pdf` |
| `adoif add-batch <dir>` | Ingest all PDFs in a syllabus/course pack | `adoif add-batch course-packs/psy305 --course PSY305 --tag midterm` |
| `adoif list --filters` | Inspect local holdings with tag/status filters | `adoif list --tag psych --missing-pdf` |
| `adoif find` / `adoif search` | Query PubMed/OpenAlex or local FTS index | `adoif find "ketamine depression" --sources pubmed,openalex` |
| `adoif config --json` | Print resolved settings for scripts/tests | `adoif config --json` |
| `adoif screen …` | Manage PRISMA-style screening queue | `adoif screen start --query "psychology residency"` |
| `adoif extract …` | Capture PICO-style notes per DOI | `adoif extract record --doi 10.1001/jama.2019.0018` |
| `adoif schedule …` | Import due dates or list upcoming readings | `adoif schedule import data/syllabus.csv --course PSY305` |
| `adoif note add` | Attach reflections/highlights | `adoif note add --doi 10.1038/... --text "Journal club takeaways"` |
| `adoif demo-report` | Generate a Markdown admissions summary | `adoif demo-report --output portfolio.md` |
| `adoif export --format bibtex` | Export citations by tag | `adoif export --format bibtex --tag psych` |
| `adoif verify --all` | Flag retracted/updated DOIs | `adoif verify --all` |
| `adoif serve` | Launch the local HTMX dashboard | `adoif serve --host 127.0.0.1 --port 8000` |

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

## Development workflow

```bash
pip install -e .[dev]
./scripts/run-tests.sh -q
```

The helper script keeps pytest’s cache enabled for faster local runs and only appends `-p no:cacheprovider` when the filesystem rejects `.pytest_cache/` (e.g., sandboxed runners). CI (`.github/workflows/ci.yml`) already runs `pytest -q` on Python 3.11 and 3.12 so PRs inherit the same behavior.

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
