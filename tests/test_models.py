from adoif.models import Author


def test_author_full_name() -> None:
    author = Author(given_name="Ada", family_name="Lovelace")
    assert author.full_name == "Ada Lovelace"
