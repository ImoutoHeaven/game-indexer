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


def _extract_library_id(body: str) -> str:
    match = re.search(r'href="/libraries/(\d+)"', body)
    assert match
    return match.group(1)


def test_library_crud_ui(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    _login(client)
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
    assert response.headers["location"] == "/libraries"

    response = client.get("/libraries", follow_redirects=False)

    assert response.status_code == 200
    assert "Primary Library" in response.text
    assert "primary-index" in response.text
    assert "Main games library" in response.text

    library_id = _extract_library_id(response.text)

    response = client.get(f"/libraries/{library_id}", follow_redirects=False)

    assert response.status_code == 200
    assert "Primary Library" in response.text
    assert "primary-index" in response.text
    assert "Main games library" in response.text

    response = client.post(
        f"/libraries/{library_id}/delete",
        data={"csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/libraries"

    response = client.get("/libraries", follow_redirects=False)

    assert response.status_code == 200
    assert "No libraries yet." in response.text


def test_library_create_requires_name(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    _login(client)
    csrf_token = _csrf_token(client)

    response = client.post(
        "/libraries/create",
        data={
            "name": "   ",
            "index_uid": "primary-index",
            "description": "Main games library",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Name is required" in response.text


def test_library_delete_missing_returns_404(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    _login(client)
    csrf_token = _csrf_token(client)

    response = client.post(
        "/libraries/999/delete",
        data={"csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 404


def test_library_create_requires_csrf(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    _login(client)

    response = client.post(
        "/libraries/create",
        data={
            "name": "Primary Library",
            "index_uid": "primary-index",
            "description": "Main games library",
        },
        follow_redirects=False,
    )

    assert response.status_code == 403


def test_library_create_duplicate_returns_error(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    _login(client)
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

    response = client.post(
        "/libraries/create",
        data={
            "name": "Primary Library",
            "index_uid": "primary-index",
            "description": "Another library",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "already exists" in response.text
