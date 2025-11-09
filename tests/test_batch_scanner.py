from pathlib import Path

from pypdf import PdfWriter

from adoif.services.batch import BatchScanner


def _write_pdf(path: Path, *, title: str | None = None, subject: str | None = None) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    metadata: dict[str, str] = {}
    if title:
        metadata["/Title"] = title
    if subject:
        metadata["/Subject"] = subject
    if metadata:
        writer.add_metadata(metadata)
    with path.open("wb") as handle:
        writer.write(handle)


def test_batch_scanner_uses_pdf_metadata(tmp_path) -> None:
    pdf_path = tmp_path / "study.pdf"
    _write_pdf(pdf_path, title="Psych Study", subject="doi 10.1000/xyz")

    scanner = BatchScanner()
    candidates = scanner.scan(tmp_path)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.title == "Psych Study"
    assert candidate.doi == "10.1000/xyz"
    assert candidate.identifier == "10.1000/xyz"


def test_batch_scanner_falls_back_to_filename(tmp_path) -> None:
    pdf_path = tmp_path / "week1-reading.pdf"
    _write_pdf(pdf_path)

    scanner = BatchScanner()
    candidates = scanner.scan(tmp_path)

    assert candidates[0].title == "week1-reading"
    assert candidates[0].doi is None
