"""Utilities for scanning local course packs and preparing batch ingest jobs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import structlog
from pypdf import PdfReader

from adoif.utils import extract_doi, slugify

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class BatchCandidate:
    path: Path
    title: str
    identifier: str
    doi: str | None = None


class BatchScanner:
    """Scan a directory for PDFs and extract lightweight metadata."""

    def __init__(self, *, min_title_length: int = 5) -> None:
        self._min_title_length = min_title_length

    def scan(self, directory: Path, *, limit: int | None = None) -> list[BatchCandidate]:
        if not directory.is_dir():
            raise ValueError(f"{directory} is not a directory")
        pdfs = sorted(p for p in directory.rglob("*.pdf") if p.is_file())
        if limit is not None:
            pdfs = pdfs[:limit]
        candidates: list[BatchCandidate] = []
        for pdf in pdfs:
            title, doi = self._extract_metadata(pdf)
            identifier = doi or f"manual-{slugify(pdf.stem)}"
            candidates.append(BatchCandidate(path=pdf, title=title, identifier=identifier, doi=doi))
        return candidates

    def _extract_metadata(self, path: Path) -> tuple[str, str | None]:
        title = path.stem
        doi: str | None = None
        try:
            reader = PdfReader(str(path))
        except Exception as exc:  # pragma: no cover - best effort parsing
            logger.warning("batch.pdf_read_failed", path=str(path), error=str(exc))
            return title, None
        info = reader.metadata or {}
        if info:
            raw_title = getattr(info, "title", None) or info.get("/Title")
            if raw_title and len(raw_title.strip()) >= self._min_title_length:
                title = raw_title.strip()
            metadata_blob = " ".join(str(value) for value in info.values() if value)
            doi = extract_doi(metadata_blob)
        if doi is None:
            page_text = self._first_page_text(reader)
            if page_text:
                derived_title = self._first_nonempty_line(page_text)
                if derived_title:
                    title = derived_title
                doi = extract_doi(page_text)
        return title, doi

    def _first_page_text(self, reader: PdfReader) -> str:
        try:
            page = reader.pages[0]
        except (IndexError, KeyError):
            return ""
        try:
            text = page.extract_text() or ""
        except Exception:  # pragma: no cover - backend differences
            return ""
        return text

    def _first_nonempty_line(self, text: str) -> str | None:
        for line in text.splitlines():
            candidate = line.strip()
            if len(candidate) >= self._min_title_length:
                return candidate
        return None


def summarize_candidates(candidates: Iterable[BatchCandidate]) -> list[tuple[str, str]]:
    """Return `(filename, title)` tuples for console output."""

    summary: list[tuple[str, str]] = []
    for item in candidates:
        summary.append((item.path.name, item.title))
    return summary
