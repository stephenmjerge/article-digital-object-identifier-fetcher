from datetime import datetime

from adoif.models import ArticleMetadata, StoredArtifact
from adoif.reporting import ReportData, ScreeningSnapshot, build_demo_report
from adoif.services.notes import Note
from adoif.services.schedule import ScheduleEntry
from adoif.db import ExtractionRecord


def _artifact(title: str) -> StoredArtifact:
    metadata = ArticleMetadata(doi="10.1/demo", title=title, tags=["psych"])
    return StoredArtifact(metadata=metadata)


def test_build_demo_report_includes_sections(tmp_path) -> None:
    extraction = ExtractionRecord(doi="10.1/demo", status="completed")
    note = Note(id=1, doi="10.1/demo", body="Great study", tags=["PSY305"], created_at=datetime.utcnow())
    schedule = ScheduleEntry(id=1, course="PSY305", title="Week 1", doi="10.1/demo", due_date=datetime.utcnow())
    data = ReportData(
        artifacts=[_artifact("Demo")],
        screening=[ScreeningSnapshot(name="Trial", included=1, excluded=0, pending=0)],
        extractions=[extraction],
        notes=[note],
        schedule=[schedule],
    )
    report = build_demo_report(data)
    assert "Library Snapshot" in report
    assert "Screening Progress" in report
    assert "Notes & Reflections" in report
