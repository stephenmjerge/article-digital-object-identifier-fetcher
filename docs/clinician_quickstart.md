# ADOIF Clinician/Ops Quickstart

## 1) Install
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install https://github.com/stephenmjerge/article-digital-object-identifier-fetcher/releases/latest/download/adoif-0.3.0-py3-none-any.whl
```

## 2) Fast demo
```bash
adoif demo
```
Outputs: `outputs/adoif_demo_*/metadata.csv`, `metadata.json`, `report.html`, `manifest.json`.

## 3) Typical ingest
```bash
adoif add 10.1038/s41591-021-01627-4 --tag psych --dry-run
adoif add 10.1038/s41591-021-01627-4 --tag psych --pdf demo-assets/sample-article.pdf
```
HTML summaries land under `outputs/reports/`.

## 4) Environment check
```bash
adoif doctor
```

## 5) Headless/locked-down hints
- Set `ADOIF_DATA_DIR` to a writable path (defaults to `~/adoif-library`).
- If plotting/headless issues appear, set:  
  `export MPLCONFIGDIR=$PWD/.cache/mpl`  
  `export XDG_CACHE_HOME=$PWD/.cache/xdg`

## 6) Ethics & safety
- Respect copyright when attaching PDFs; fetch open-access first.
- Keep PHI/PII out of notes and uploads; use synthetic/demo data for demos.

## 7) Share safely
Share only outputs (CSV/JSON/HTML) plus the manifest; avoid raw `.env` or private PDFs unless permitted.
