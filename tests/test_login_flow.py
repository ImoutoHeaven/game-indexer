import sqlite3

from fastapi.testclient import TestClient

from game_web import app as app_module
from game_web.app import create_app


def test_login_sets_session_cookie_and_persists_session(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    response = client.post(
        "/login",
        json={"username": "admin", "password": "admin"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/libraries"
    session_id = response.cookies.get("session")
    assert session_id

    assert "SameSite=Lax" in response.headers.get("set-cookie", "")

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

    response = client.post(
        "/login",
        json={"username": "admin", "password": "wrong"},
        follow_redirects=False,
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid credentials"}
    assert response.cookies.get("session") is None
    assert "set-cookie" not in response.headers


def test_login_handles_session_error(tmp_path, monkeypatch, caplog):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    def _raise_error(*args, **kwargs):
        raise RuntimeError("db failure")

    monkeypatch.setattr(app_module, "create_session", _raise_error)

    with caplog.at_level("ERROR"):
        response = client.post(
            "/login",
            json={"username": "admin", "password": "admin"},
            follow_redirects=False,
        )

    assert response.status_code == 500
    assert response.json() == {"detail": "session creation failed"}
    assert response.cookies.get("session") is None
    assert "set-cookie" not in response.headers
    assert "session creation failed" in caplog.text
    assert "db failure" in caplog.text
