import sqlite3

from fastapi.testclient import TestClient

import game_web.routes.auth as auth_routes
from game_web.app import create_app


def _csrf_token(client: TestClient) -> str:
    token = client.cookies.get("csrf_token")
    assert token
    return token


def _setup_admin(client: TestClient) -> None:
    response = client.get("/setup", follow_redirects=False)
    assert response.status_code == 200
    csrf_token = _csrf_token(client)
    response = client.post(
        "/setup",
        data={"password": "secret123", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 302


def _login_admin(client: TestClient) -> None:
    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 200
    csrf_token = _csrf_token(client)
    response = client.post(
        "/login",
        data={"password": "secret123", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 302


def test_login_sets_session_cookie_and_persists_session(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    _setup_admin(client)
    _login_admin(client)
    session_id = client.cookies.get("session")
    assert session_id

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute("select id, user_id, created_at, expires_at from session")
        row = cur.fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row[0] == session_id
    assert row[1] == 1
    assert "+00:00" in row[2]
    assert "+00:00" in row[3]


def test_login_rejects_invalid_credentials(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    _setup_admin(client)
    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 200
    csrf_token = _csrf_token(client)
    response = client.post(
        "/login",
        data={"password": "wrong", "csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Invalid password" in response.text
    assert response.cookies.get("session") is None


def test_login_handles_session_error(tmp_path, monkeypatch, caplog):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    def _raise_error(*args, **kwargs):
        raise RuntimeError("db failure")

    _setup_admin(client)
    monkeypatch.setattr(auth_routes, "create_session", _raise_error)

    csrf_token = _csrf_token(client)
    with caplog.at_level("ERROR"):
        response = client.post(
            "/login",
            data={"password": "secret123", "csrf_token": csrf_token},
            follow_redirects=False,
        )

    assert response.status_code == 500
    assert "Session creation failed" in response.text
    assert response.cookies.get("session") is None
