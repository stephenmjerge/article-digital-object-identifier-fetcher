from pathlib import Path

import pytest

from adoif.models import ArticleMetadata, Author, FetchRequest, FetchResult
from adoif.services.pdf_fetcher import PDFDownload
from adoif.services.pipeline import IngestPipeline, ManualOverrides
from adoif.services.resolvers import ResolverRegistry
from adoif.services.storage import LocalLibrary
from adoif.settings import Settings


class _StubResolver:
    name = "stub"

    def __init__(self, metadata: ArticleMetadata) -> None:
        self._metadata = metadata

    async def resolve(self, request: FetchRequest) -> FetchResult | None:  # noqa: D401 - test helper
        return FetchResult(metadata=self._metadata, provider=self.name)


class _StubFetcher:
    async def fetch(self, doi: str, target: Path) -> PDFDownload | None:  # noqa: D401 - test helper
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"%PDF-1.4 test")
        return PDFDownload(path=target, source="stub-fetch", license=None, host_type="api")


@pytest.mark.asyncio
async def test_pipeline_uses_manual_overrides_when_resolvers_fail(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    storage = LocalLibrary(settings)
    registry = ResolverRegistry([])
    pipeline = IngestPipeline(registry=registry, storage=storage, pdf_fetcher=None)

    overrides = ManualOverrides(title="Manual Title", journal="Test Journal", tags=("psych",))
    outcome = await pipeline.ingest(
        request=FetchRequest(identifier="custom-id"),
        overrides=overrides,
        persist=False,
    )

    assert outcome.artifact.metadata.title == "Manual Title"
    assert outcome.artifact.metadata.journal == "Test Journal"
    assert "psych" in outcome.artifact.metadata.tags


def _resolver_with_metadata() -> _StubResolver:
    metadata = ArticleMetadata(
        doi="10.1/demo",
        title="Demo Article",
        journal="Demo Journal",
        authors=[Author(given_name="Ada", family_name="Lovelace")],
    )
    return _StubResolver(metadata)


@pytest.mark.asyncio
async def test_pipeline_downloads_pdf_when_fetcher_available(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    storage = LocalLibrary(settings)
    registry = ResolverRegistry([_resolver_with_metadata()])
    fetcher = _StubFetcher()
    pipeline = IngestPipeline(registry=registry, storage=storage, pdf_fetcher=fetcher)

    outcome = await pipeline.ingest(request=FetchRequest(identifier="10.1/demo"), overrides=None)

    assert outcome.pdf_saved
    assert outcome.artifact.pdf_path is not None
    assert outcome.artifact.pdf_path.exists()


@pytest.mark.asyncio
async def test_pipeline_attaches_local_pdf(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    storage = LocalLibrary(settings)
    registry = ResolverRegistry([_resolver_with_metadata()])
    pipeline = IngestPipeline(registry=registry, storage=storage, pdf_fetcher=None)

    sample_pdf = tmp_path / "demo.pdf"
    sample_pdf.write_bytes(b"%PDF-1.4 test")

    outcome = await pipeline.ingest(
        request=FetchRequest(identifier="10.1/demo"),
        overrides=None,
        local_pdf=sample_pdf,
    )

    assert outcome.pdf_saved
    assert outcome.artifact.pdf_path is not None
    assert outcome.artifact.pdf_path.exists()
