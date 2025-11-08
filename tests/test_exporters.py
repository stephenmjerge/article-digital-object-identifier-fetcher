from datetime import datetime

from adoif.exporters import export_bibtex, export_csl_json
from adoif.models import ArticleMetadata, Author, StoredArtifact


def _sample_artifact() -> StoredArtifact:
    metadata = ArticleMetadata(
        doi="10.1000/xyz123",
        title="Sample Study",
        authors=[Author(given_name="Ada", family_name="Lovelace")],
        journal="Journal of Tests",
        publication_date=datetime(2021, 5, 17),
        tags=["psych"],
    )
    return StoredArtifact(metadata=metadata)


def test_bibtex_export_contains_expected_fields() -> None:
    artifact = _sample_artifact()
    result = export_bibtex([artifact])
    assert "@article" in result
    assert "Sample Study" in result
    assert "doi" in result.lower()


def test_csl_export_serializes_to_json() -> None:
    artifact = _sample_artifact()
    result = export_csl_json([artifact])
    assert "Sample Study" in result
    assert "Journal of Tests" in result
