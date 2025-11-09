from fastapi.testclient import TestClient

from adoif.settings import Settings
from adoif.web.app import create_app


def test_dashboard_home_loads(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200


def test_insights_page_loads(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)
    client = TestClient(app)
    response = client.get("/insights")
    assert response.status_code == 200


def test_notes_page_lists_and_creates(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    response = client.post(
        "/notes",
        data={
            "doi": "10.1/demo",
            "body": "Great methods section",
            "tags": "psy305, reflection",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    response = client.get("/notes")
    assert response.status_code == 200
    assert "Great methods section" in response.text
