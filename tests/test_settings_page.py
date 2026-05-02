import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from game_web.app import create_app
from game_web.secrets import encrypt_secret


class FakeBrokenClient:
    def __init__(self, _url: str, _api_key: str | None):
        pass

    def health(self) -> dict[str, str]:
        raise RuntimeError("boom")


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


def test_settings_blank_api_key_clears_saved_key(tmp_path):
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

    conn = sqlite3.connect(tmp_path / "app.db")
    try:
        row = conn.execute(
            "select value from settings where key = ?",
            ("meili_api_key",),
        ).fetchone()
    finally:
        conn.close()

    response = client.get("/settings", follow_redirects=False)

    assert response.status_code == 200
    assert row is None
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


def test_settings_save_reports_saved_but_connection_failed(tmp_path, monkeypatch):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app)

    _login(client)
    monkeypatch.setattr(
        "game_web.services.meili_health_service.meilisearch.Client",
        FakeBrokenClient,
    )
    csrf_token = _csrf_token(client)

    response = client.post(
        "/settings",
        data={
            "meili_url": "http://127.0.0.1:7700",
            "meili_api_key": "masterKey",
            "csrf_token": csrf_token,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Saved, but connection failed" in response.text


def test_settings_nav_is_visible_after_login(tmp_path):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app)

    _login(client)

    response = client.get("/libraries", follow_redirects=False)

    assert response.status_code == 200
    assert "Settings" in response.text
    assert response.text.index("Libraries") < response.text.index("Jobs")
    assert response.text.index("Jobs") < response.text.index("Search")
    assert response.text.index("Search") < response.text.index("Settings")
    assert response.text.index("Settings") < response.text.index("Logout")


def test_settings_page_keeps_only_url_and_api_key_inputs(tmp_path):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app)

    _login(client)

    response = client.get("/settings", follow_redirects=False)

    assert response.status_code == 200
    assert 'name="meili_url"' in response.text
    assert 'name="meili_api_key"' in response.text
    assert 'name="clear_api_key"' not in response.text
    assert "Leave this blank and save to clear the stored API key" in response.text


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


def test_settings_persistence_failure_shows_save_failed(tmp_path, monkeypatch):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app, raise_server_exceptions=False)

    _login(client)

    def _raise(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr("game_web.routes.settings.set_setting", _raise)
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

    assert response.status_code == 500
    assert "Save failed" in response.text


def test_settings_commit_failure_shows_save_failed(tmp_path, monkeypatch):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app, raise_server_exceptions=False)

    _login(client)

    import game_web.routes.settings as settings_routes

    original_connect_db = settings_routes.connect_db

    class CommitFailingConnection:
        def __init__(self, conn):
            self._conn = conn

        def commit(self):
            raise RuntimeError("commit failed")

        def __getattr__(self, name):
            return getattr(self._conn, name)

    def _connect_with_commit_failure(db_path: str):
        return CommitFailingConnection(original_connect_db(db_path))

    monkeypatch.setattr(settings_routes, "connect_db", _connect_with_commit_failure)
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

    assert response.status_code == 500
    assert "Save failed" in response.text
