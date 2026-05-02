import sqlite3
import re

import pytest
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
    response = client.post(
        "/libraries/create",
        data={
            "name": "Primary Library",
            "index_uid": "primary-index",
            "description": "Main games library",
            "csrf_token": _csrf_token(client),
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    response = client.get("/libraries", follow_redirects=False)
    assert response.status_code == 200
    match = re.search(r'href="/libraries/(\d+)"', response.text)
    assert match
    return match.group(1)


def test_libraries_page_renders_after_login(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    _login(client)

    response = client.get("/libraries", follow_redirects=False)

    assert response.status_code == 200
    assert "Libraries" in response.text


def test_libraries_page_shows_settings_reminder_when_meili_unreachable(tmp_path):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app)

    _login(client)

    response = client.get("/libraries", follow_redirects=False)

    assert response.status_code == 200
    assert "Open settings" in response.text
    assert "Meilisearch" in response.text


def test_library_create_redirect_displays_success_notice(tmp_path):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app)

    _login(client)

    response = client.post(
        "/libraries/create",
        data={
            "name": "Primary Library",
            "index_uid": "primary-index",
            "description": "Main games library",
            "csrf_token": _csrf_token(client),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Library created" in response.text


def test_library_delete_redirect_displays_destructive_notice(tmp_path):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app)

    _login(client)
    library_id = _create_library(client)

    response = client.post(
        f"/libraries/{library_id}/delete",
        data={"csrf_token": _csrf_token(client)},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Library deleted" in response.text


@pytest.mark.parametrize(
    "failure",
    [
        OSError("disk full"),
        sqlite3.DatabaseError("database locked"),
    ],
)
def test_library_delete_failure_redirects_with_error_notice(tmp_path, monkeypatch, failure):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app, raise_server_exceptions=False)

    _login(client)
    library_id = _create_library(client)

    def _boom(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr("game_web.routes.library.delete_library", _boom)

    response = client.post(
        f"/libraries/{library_id}/delete",
        data={"csrf_token": _csrf_token(client)},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert response.request.url.path == "/libraries"
    assert "Library delete failed" in response.text
    assert "Library deleted" not in response.text
