import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from game_web.app import create_app
from game_web.secrets import encrypt_secret


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


def test_settings_persist_meili_url(tmp_path):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app)

    _login(client)
    csrf_token = _csrf_token(client)

    response = client.post(
        "/settings",
        data={
            "meili_url": "http://127.0.0.1:7700",
            "meili_api_key": "masterKey",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    conn = sqlite3.connect(tmp_path / "app.db")
    try:
        row = conn.execute(
            "select value from settings where key = ?",
            ("meili_api_key",),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row[0] != "masterKey"
    assert row[0]

    response = client.get("/settings", follow_redirects=False)

    assert response.status_code == 200
    assert "http://127.0.0.1:7700" in response.text
    assert "masterKey" not in response.text
    assert "API key status: Set" in response.text
    assert "API key status: Not set" not in response.text


def test_settings_does_not_clear_api_key_on_empty(tmp_path):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app)

    _login(client)
    csrf_token = _csrf_token(client)

    response = client.post(
        "/settings",
        data={
            "meili_url": "http://127.0.0.1:7700",
            "meili_api_key": "masterKey",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    csrf_token = _csrf_token(client)
    response = client.post(
        "/settings",
        data={
            "meili_url": "http://127.0.0.1:7700",
            "meili_api_key": "",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    response = client.get("/settings", follow_redirects=False)

    assert response.status_code == 200
    assert "masterKey" not in response.text
    assert "API key status: Set" in response.text
    assert "API key status: Not set" not in response.text


def test_settings_can_clear_api_key(tmp_path):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app)

    _login(client)
    csrf_token = _csrf_token(client)

    response = client.post(
        "/settings",
        data={
            "meili_url": "http://127.0.0.1:7700",
            "meili_api_key": "masterKey",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    csrf_token = _csrf_token(client)
    response = client.post(
        "/settings",
        data={
            "meili_url": "http://127.0.0.1:7700",
            "meili_api_key": "",
            "clear_api_key": "1",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    response = client.get("/settings", follow_redirects=False)

    assert response.status_code == 200
    assert "API key status: Not set" in response.text
    assert "API key status: Set" not in response.text


def test_settings_clear_does_not_override_new_key(tmp_path):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app)

    _login(client)
    csrf_token = _csrf_token(client)

    response = client.post(
        "/settings",
        data={
            "meili_url": "http://127.0.0.1:7700",
            "meili_api_key": "oldKey",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    csrf_token = _csrf_token(client)
    response = client.post(
        "/settings",
        data={
            "meili_url": "http://127.0.0.1:7700",
            "meili_api_key": "newKey",
            "clear_api_key": "1",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    conn = sqlite3.connect(tmp_path / "app.db")
    try:
        row = conn.execute(
            "select value from settings where key = ?",
            ("meili_api_key",),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row[0]

    response = client.get("/settings", follow_redirects=False)

    assert response.status_code == 200
    assert "API key status: Set" in response.text
    assert "API key status: Not set" not in response.text


def test_settings_invalid_api_key_shows_invalid(tmp_path):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app)

    _login(client)
    data_dir = Path(tmp_path)
    encrypt_secret(data_dir, "seed")
    conn = sqlite3.connect(tmp_path / "app.db")
    try:
        conn.execute(
            "insert into settings (key, value, updated_at) values (?, ?, ?)",
            ("meili_api_key", "not-a-token", "2026-02-02T00:00:00+00:00"),
        )
        conn.commit()
    finally:
        conn.close()

    response = client.get("/settings", follow_redirects=False)

    assert response.status_code == 200
    assert "API key status: Invalid" in response.text


def test_settings_missing_key_file_shows_reset_required(tmp_path):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app)

    _login(client)
    conn = sqlite3.connect(tmp_path / "app.db")
    try:
        conn.execute(
            "insert into settings (key, value, updated_at) values (?, ?, ?)",
            ("meili_api_key", "not-a-token", "2026-02-02T00:00:00+00:00"),
        )
        conn.commit()
    finally:
        conn.close()

    response = client.get("/settings", follow_redirects=False)

    assert response.status_code == 200
    assert "API key status: Reset required" in response.text


def test_settings_encrypt_error_returns_400(tmp_path, monkeypatch):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app)

    _login(client)

    def _raise(*args, **kwargs):
        raise OSError("encrypt failed")

    monkeypatch.setattr("game_web.routes.settings.encrypt_secret", _raise)
    csrf_token = _csrf_token(client)

    response = client.post(
        "/settings",
        data={
            "meili_url": "http://127.0.0.1:7700",
            "meili_api_key": "masterKey",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Failed to save API key" in response.text
