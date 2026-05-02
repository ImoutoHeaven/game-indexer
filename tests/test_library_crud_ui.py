import re

from fastapi.testclient import TestClient

from game_web.app import create_app
from game_web.db import connect_db
from game_web.services import dataset_service, job_service, library_service
from game_web.services.settings_service import set_setting


class FakeHealthyClient:
    def __init__(self, _url: str, _api_key: str | None):
        pass

    def health(self) -> dict[str, str]:
        return {"status": "available"}


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


def _set_reachable_settings(db_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "game_web.services.meili_health_service.meilisearch.Client",
        FakeHealthyClient,
    )
    conn = connect_db(str(db_path))
    try:
        set_setting(conn, "meili_url", "http://127.0.0.1:7700")
    finally:
        conn.close()


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
    assert response.headers["location"].startswith("/libraries")

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
    assert response.headers["location"].startswith("/libraries")

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


def test_libraries_page_shows_readiness_badge_and_primary_action(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    _login(client)
    _set_reachable_settings(db_path, monkeypatch)
    csrf_token = _csrf_token(client)

    response = client.post(
        "/libraries/create",
        data={
            "name": "Primary Library",
            "index_uid": "primary-index",
            "description": "Main games library",
            "csrf_token": csrf_token,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Needs dataset" in response.text
    assert "Open library" in response.text
    assert "No dataset" in response.text
    assert "No build yet" in response.text


def test_libraries_page_uses_fixed_row_action_mapping_by_readiness(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    app.state.data_dir = tmp_path / "data"
    client = TestClient(app)

    _login(client)
    _set_reachable_settings(db_path, monkeypatch)

    conn = connect_db(str(db_path))
    try:
        library_service.create_library(
            conn,
            name="Needs Dataset",
            index_uid="needs-dataset",
            description="Pending upload",
        )
        library_service.create_library(
            conn,
            name="Queued Library",
            index_uid="queued-index",
            description="Queued build",
        )
        queued_dataset = dataset_service.create_dataset(
            conn,
            data_dir=app.state.data_dir,
            library_id=2,
            filename="queued.txt",
            content=b"A\n",
        )
        job_service.create_job(
            conn,
            library_id=2,
            dataset_id=int(queued_dataset["id"]),
            job_type="build",
            status="queued",
        )
        library_service.create_library(
            conn,
            name="Search Ready",
            index_uid="search-index",
            description="Finished build",
        )
        done_dataset = dataset_service.create_dataset(
            conn,
            data_dir=app.state.data_dir,
            library_id=3,
            filename="done.txt",
            content=b"B\n",
        )
        job_service.create_job(
            conn,
            library_id=3,
            dataset_id=int(done_dataset["id"]),
            job_type="build",
            status="done",
        )
    finally:
        conn.close()

    response = client.get("/libraries", follow_redirects=False)

    assert response.status_code == 200
    assert "Open settings" in response.text
    assert "Open library" in response.text
    assert "View jobs" in response.text
    assert "Search" in response.text


def test_libraries_page_delete_action_is_visibly_destructive(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    _login(client)
    _set_reachable_settings(db_path, monkeypatch)
    csrf_token = _csrf_token(client)

    response = client.post(
        "/libraries/create",
        data={
            "name": "Primary Library",
            "index_uid": "primary-index",
            "description": "Main games library",
            "csrf_token": csrf_token,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Delete" in response.text
    assert "removes local datasets and logs" in response.text
