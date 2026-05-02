import re

from fastapi.testclient import TestClient

from game_web.app import create_app


def _csrf_token(client: TestClient) -> str:
    token = client.cookies.get("csrf_token")
    assert token
    return token


def _login(client: TestClient) -> None:
    response = client.get("/setup", follow_redirects=False)
    assert response.status_code == 200
    csrf_token = _csrf_token(client)
    response = client.post(
        "/setup",
        data={"password": "secret123", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 302
    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 200
    csrf_token = _csrf_token(client)
    response = client.post(
        "/login",
        data={"password": "secret123", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 302


def _create_library(client: TestClient) -> str:
    csrf_token = _csrf_token(client)
    response = client.post(
        "/libraries/create",
        data={
            "name": "Primary Library",
            "index_uid": "primary-index",
            "description": "Main games library",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    response = client.get("/libraries", follow_redirects=False)
    assert response.status_code == 200
    match = re.search(r'href="/libraries/(\d+)"', response.text)
    assert match
    return match.group(1)


def test_library_detail_edits_single_active_search_config(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    _login(client)
    library_id = _create_library(client)
    csrf_token = _csrf_token(client)

    response = client.post(
        f"/libraries/{library_id}/search-config",
        data={
            "model_name": "BAAI/bge-m3",
            "use_fp16": "0",
            "max_length": "128",
            "csrf_token": csrf_token,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Search Configuration" in response.text
    assert "Profile key" not in response.text
    assert "Variant" not in response.text
    assert "Enabled" not in response.text
