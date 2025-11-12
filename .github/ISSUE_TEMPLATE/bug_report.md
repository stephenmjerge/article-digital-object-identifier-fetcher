---
name: Bug report
about: Report a reproducible defect in ADOIF’s CLI, ingestion pipeline, or dashboard.
title: "[BUG] "
labels: ["bug"]
assignees: []
---

## Summary
Describe the issue and how it blocks literature ingest, demo recordings, or admissions workflows.

## Reproduction checklist
- [ ] Reproduces on current `main`
- [ ] Tested in a clean env (`pip install -e .[dev]`)
- [ ] Includes sample DOIs / PDFs / config

### Steps to reproduce
1. …
2. …

### Sample command / request
```bash
adoif ... # include full CLI command or API call
```

## Expected vs. actual
- **Expected:** …
- **Actual:** …

## Environment
- OS / version:
- Python version:
- Data location (`.adoif-data`, custom paths):
- External services used (PubMed, OpenAlex, Unpaywall, etc.):
- Additional settings (`.env`, config flags):

## Logs / artifacts
Attach stack traces, screenshots, CLI output, or GitHub Actions job links.
