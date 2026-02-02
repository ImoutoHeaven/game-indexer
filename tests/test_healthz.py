from fastapi.testclient import TestClient

from game_web.app import create_app


def test_healthz_returns_ok(tmp_path):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app)

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
