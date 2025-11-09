# ADOIF Quickstart Demo

This walkthrough seeds a small, local research library in under ten minutes so you can show admissions committees a working evidence workflow. All commands run locally—no cloud services or external databases.

## 1. Environment setup
1. Create an isolated environment and install ADOIF:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e .
   ```
2. Point ADOIF at a demo library directory and set your Unpaywall email (required for real PDF downloads):
   ```bash
   export ADOIF_DATA_DIR="$(pwd)/.adoif-data"
   export ADOIF_UNPAYWALL_EMAIL="you@example.com"
   ```
3. Bootstrap the directory structure:
   ```bash
   adoif init
   ```

## 2. Ingest your first article
Use a known DOI or PMID. To keep the demo self-contained, attach the included sample PDF:
```bash
adoif add 10.1038/s41586-020-2649-2 \
  --tag psych --tag methods \
  --pdf demo-assets/sample-article.pdf
```
- Pass `--dry-run` first if you want to preview metadata without writing to disk.
- When you are online and have `ADOIF_UNPAYWALL_EMAIL` set, omit `--pdf` and ADOIF will pull the open-access PDF from Unpaywall automatically.

## 3. Batch-ingest a course pack (optional)
Drop a few PDFs into `course-packs/psy305` (filenames become fallbacks for titles) and run:
```bash
adoif add-batch course-packs/psy305 --course PSY305 --tag baker-college
```
ADOIF scans each PDF for metadata, derives best-effort titles, attaches the local file, and applies the course tags so you can filter by class later. Add `--dry-run` to preview what would be imported.

## 4. Inspect the library
```bash
adoif list
adoif search "psych"
adoif export --format bibtex --output demo.bib
adoif verify --all
```
These commands prove that metadata, FTS search, export, and Crossref verification all work end-to-end.

## 5. Run a screening sprint
1. Seed a project with PubMed + OpenAlex hits:
   ```bash
   adoif screen start --name "psych-trials" \
     --query "depression psychotherapy" --sources pubmed,openalex --limit 20
   ```
2. Review candidates:
   ```bash
   adoif screen candidates --project-id 1 --status all
   adoif screen label --candidate-id 1 --label include --reason "RCT"
   adoif screen prisma --project-id 1
   ```
This gives you PRISMA-style numbers to showcase disciplined triage.

## 6. Capture PICO extractions
Record structured notes for an accepted paper:
```bash
adoif extract record --doi 10.1038/s41586-020-2649-2 \
  --population "Adults" --intervention "CBT" --comparator "TAU" \
  --outcomes "Improved PHQ-9" --status completed
adoif extract list
```
Optional: append statistical outcomes with `--effect-size`, `--ci-low`, etc.

## 7. Launch the dashboard
Bring everything together visually:
```bash
adoif serve --host 127.0.0.1 --port 8000
```
Visit `http://127.0.0.1:8000` to walk reviewers through the Library, Screening, Extractions, and Insights tabs.

## 8. Reset between demos
Remove the data directory when you want a clean slate:
```bash
rm -rf "$ADOIF_DATA_DIR"
```

Show screenshots or short recordings of each stage alongside your application to highlight reproducible habits.
