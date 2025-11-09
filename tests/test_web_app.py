from fastapi.testclient import TestClient

from adoif.settings import Settings
from adoif.web.app import create_app


def test_dashboard_home_loads(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
