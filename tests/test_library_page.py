from fastapi.testclient import TestClient

from game_web.app import create_app


def test_libraries_requires_login(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    response = client.get("/libraries", follow_redirects=False)

    assert response.status_code == 401
    assert response.headers.get("location") is None
