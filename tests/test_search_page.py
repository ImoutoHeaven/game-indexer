from fastapi.testclient import TestClient

from game_web.app import create_app


def test_search_page_renders_ok(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    response = client.get("/search", follow_redirects=False)

    assert response.status_code == 200
    body = response.text
    assert "Search" in body
    assert "Library" in body
    assert "Embedder" in body
    assert "action=\"/search\"" in body
