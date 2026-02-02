from fastapi.testclient import TestClient

from game_web.app import create_app


def test_libraries_redirects_to_login_when_logged_out(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    response = client.get("/libraries", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"


def test_search_redirects_to_login_when_logged_out(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    response = client.get("/search", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers.get("location") == "/login"
