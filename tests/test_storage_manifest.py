import asyncio
from pathlib import Path

import pytest

from adoif.models import ArticleMetadata, StoredArtifact
from adoif.services.storage import LocalLibrary
from adoif.settings import Settings


@pytest.mark.asyncio
async def test_register_pdf_moves_file_and_updates_manifest(tmp_path: Path) -> None:
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
    )

    assert final_path.exists()
    assert checksum

    artifact = StoredArtifact(
        metadata=ArticleMetadata(doi="10.1000/foo", title="Test", tags=[])
    )
    await storage.upsert(artifact)

    # Second register should detect existing file and not raise
    temp2 = storage.temp_pdf_path("10.1000/foo")
    temp2.parent.mkdir(parents=True, exist_ok=True)
    temp2.write_bytes(b"example pdf bytes")
    final_path2, checksum2 = await storage.register_pdf(
        doi="10.1000/foo",
        temp_path=temp2,
        source="unpaywall",
        license=None,
    )
    assert final_path == final_path2
    assert checksum == checksum2
