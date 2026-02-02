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


def test_default_profile_created_on_library(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    _login(client)
    library_id = _create_library(client)

    response = client.get(f"/libraries/{library_id}", follow_redirects=False)

    assert response.status_code == 200
    assert "Embedding profiles" in response.text
    assert "default" in response.text


def test_create_profile_from_library_detail(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    _login(client)
    library_id = _create_library(client)
    csrf_token = _csrf_token(client)

    response = client.post(
        f"/libraries/{library_id}/profiles/create",
        data={
            "key": "v_name",
            "model_name": "BAAI/bge-m3",
            "use_fp16": "1",
            "max_length": "256",
            "variant": "norm",
            "enabled": "1",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == f"/libraries/{library_id}"

    response = client.get(f"/libraries/{library_id}", follow_redirects=False)

    assert response.status_code == 200
    assert "default" in response.text
    assert "v_name" in response.text
    assert "BAAI/bge-m3" in response.text
    assert "256" in response.text
    assert "norm" in response.text


def test_profile_create_rejects_zero_max_length(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    _login(client)
    library_id = _create_library(client)
    csrf_token = _csrf_token(client)

    response = client.post(
        f"/libraries/{library_id}/profiles/create",
        data={
            "key": "v_name",
            "model_name": "BAAI/bge-m3",
            "use_fp16": "1",
            "max_length": "0",
            "variant": "raw",
            "enabled": "1",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Max length must be greater than 0" in response.text


def test_profile_create_rejects_invalid_enabled(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    _login(client)
    library_id = _create_library(client)
    csrf_token = _csrf_token(client)

    response = client.post(
        f"/libraries/{library_id}/profiles/create",
        data={
            "key": "v_name",
            "model_name": "BAAI/bge-m3",
            "use_fp16": "1",
            "max_length": "256",
            "variant": "raw",
            "enabled": "2",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Enabled must be 0 or 1" in response.text


def test_profile_create_rejects_duplicate_key(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    _login(client)
    library_id = _create_library(client)
    csrf_token = _csrf_token(client)

    response = client.post(
        f"/libraries/{library_id}/profiles/create",
        data={
            "key": "v_name",
            "model_name": "BAAI/bge-m3",
            "use_fp16": "1",
            "max_length": "256",
            "variant": "raw",
            "enabled": "1",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    response = client.post(
        f"/libraries/{library_id}/profiles/create",
        data={
            "key": "v_name",
            "model_name": "BAAI/bge-m3",
            "use_fp16": "1",
            "max_length": "256",
            "variant": "raw",
            "enabled": "1",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Profile key already exists" in response.text
