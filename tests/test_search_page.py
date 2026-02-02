from fastapi.testclient import TestClient

from game_web.app import create_app


def test_search_page_renders_after_login(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    response = client.get("/setup", follow_redirects=False)
    assert response.status_code == 200
    csrf_token = client.cookies.get("csrf_token")
    assert csrf_token

    response = client.post(
        "/setup",
        data={"password": "secret123", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 302

    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 200
    csrf_token = client.cookies.get("csrf_token")
    assert csrf_token

    response = client.post(
        "/login",
        data={"password": "secret123", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 302

    response = client.get("/search", follow_redirects=False)

    assert response.status_code == 200
    assert "Search" in response.text
