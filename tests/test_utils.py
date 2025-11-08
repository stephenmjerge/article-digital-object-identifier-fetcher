from adoif.utils import extract_doi, slugify


def test_extract_doi_from_url() -> None:
    identifier = "https://doi.org/10.1234/Some.Article-Title"
    assert extract_doi(identifier) == "10.1234/some.article-title"


def test_slugify_basic() -> None:
    assert slugify("Neuro Imaging & Behavior") == "neuro-imaging-behavior"
