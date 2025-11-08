from pathlib import Path

import pytest

from adoif.models import ArticleMetadata, StoredArtifact
from adoif.services.storage import LocalLibrary
from adoif.settings import Settings


@pytest.mark.asyncio
async def test_register_pdf_deduplicates_and_persists_path(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    storage = LocalLibrary(settings)

    temp = storage.temp_pdf_path("10.1000/foo")
    temp.parent.mkdir(parents=True, exist_ok=True)
    temp.write_bytes(b"example pdf bytes")

    final_path, checksum = await storage.register_pdf(
        doi="10.1000/foo",
        temp_path=temp,
        source="unpaywall",
        license="cc-by",
        host_type="publisher",
    )

    artifact = StoredArtifact(
        metadata=ArticleMetadata(doi="10.1000/foo", title="Test", tags=[]),
        pdf_path=final_path,
        checksum=checksum,
    )
    await storage.upsert(artifact)

    items = await storage.list_artifacts()
    assert items[0].checksum == checksum
    assert items[0].pdf_path == final_path

    temp2 = storage.temp_pdf_path("10.1000/foo")
    temp2.parent.mkdir(parents=True, exist_ok=True)
    temp2.write_bytes(b"example pdf bytes")

    final_path2, checksum2 = await storage.register_pdf(
        doi="10.1000/foo",
        temp_path=temp2,
        source="unpaywall",
        license=None,
        host_type="publisher",
    )

    assert final_path == final_path2
    assert checksum == checksum2


@pytest.mark.asyncio
async def test_search_returns_results(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    storage = LocalLibrary(settings)

    artifact = StoredArtifact(
        metadata=ArticleMetadata(
            doi="10.1000/bar",
            title="Neuroimaging Study",
            journal="Brain Journal",
            tags=["neuro"],
        )
    )
    await storage.upsert(artifact)

    results = await storage.search("Neuroimaging")
    assert results
    assert results[0].metadata.doi == "10.1000/bar"
