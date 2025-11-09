from adoif.services.screening import ScreeningService
from adoif.services.search import SearchResult
from adoif.settings import Settings


def _sample_result(source: str, identifier: str) -> SearchResult:
    return SearchResult(
        identifier=identifier,
        title="Sample",
        authors=["Ada"],
        journal="Journal",
        year="2024",
        url="http://example.com",
        source=source,
    )


def test_screening_service_creates_project(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    service = ScreeningService(settings)
    project = service.create_project(
        name="Test",
        query="cancer",
        sources={"pubmed"},
        notes=None,
        results=[_sample_result("pubmed", "10.1/foo"), _sample_result("openalex", "10.1/bar")],
    )
    projects = service.list_projects()
    assert projects
    candidates = service.list_candidates(project.id)
    assert len(candidates) == 2
    updated = service.update_candidate(candidates[0].id, status="include", reason="RCT")
    assert updated and updated.status == "include"
    summary = service.prisma_summary(project.id)
    assert summary.total == 2
    assert summary.included == 1
