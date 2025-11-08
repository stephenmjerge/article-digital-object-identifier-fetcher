import pytest

from adoif.models import FetchRequest
from adoif.services.pipeline import IngestPipeline, ManualOverrides
from adoif.services.resolvers import ResolverRegistry
from adoif.services.storage import LocalLibrary
from adoif.settings import Settings


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
