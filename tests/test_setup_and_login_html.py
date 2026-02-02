from fastapi.testclient import TestClient

from game_web.app import create_app


def _csrf_token(client: TestClient) -> str:
    token = client.cookies.get("csrf_token")
    assert token
    return token


def test_setup_then_login_flow(tmp_path):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app)

    resp = client.get("/login", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/setup"

    resp = client.get("/setup")
    assert resp.status_code == 200
    assert "Set admin password" in resp.text
    csrf_token = _csrf_token(client)

    resp = client.post(
        "/setup",
        data={"password": "", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "Password must be at least 8 characters" in resp.text

    resp = client.post(
        "/setup",
        data={"password": "   ", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "Password must be at least 8 characters" in resp.text

    resp = client.post(
        "/setup",
        data={"password": "short", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "Password must be at least 8 characters" in resp.text

    resp = client.post(
        "/setup",
        data={"password": "secret123", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    resp = client.post(
        "/setup",
        data={"password": "secret123", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    resp = client.get("/login")
    assert resp.status_code == 200
    csrf_token = _csrf_token(client)

    resp = client.post(
        "/login",
        data={"csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "Password is required" in resp.text

    resp = client.post(
        "/login",
        data={"password": "   ", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "Password is required" in resp.text

    resp = client.post(
        "/login",
        data={"password": "wrongpass", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "Invalid password" in resp.text

    resp = client.post(
        "/login",
        data={"password": "secret123", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "session" in resp.cookies
    assert "Max-Age=86400" in resp.headers.get("set-cookie", "")

    csrf_token = _csrf_token(client)
    resp = client.post(
        "/logout",
        data={"csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "csrf_token" not in resp.cookies


def test_auth_posts_require_csrf(tmp_path):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app)

    client.get("/setup")

    resp = client.post("/setup", data={"password": "secret123"}, follow_redirects=False)
    assert resp.status_code == 403

    client.get("/login")
    resp = client.post("/login", data={"password": "secret123"}, follow_redirects=False)
    assert resp.status_code == 403

    resp = client.post("/logout", follow_redirects=False)
    assert resp.status_code == 403
