import re
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from game_web.app import create_app
from game_web.db import connect_db


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


def test_upload_dataset_creates_job_and_lists_on_jobs_page(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app, raise_server_exceptions=False)

    _login(client)
    library_id = _create_library(client)
    csrf_token = _csrf_token(client)

    response = client.post(
        f"/libraries/{library_id}/datasets/upload",
        data={"csrf_token": csrf_token},
        files={"file": ("games.txt", b"A\nB\n")},
        follow_redirects=False,
    )

    assert response.status_code == 302

    response = client.get("/jobs", follow_redirects=False)

    assert response.status_code == 200
    assert "build" in response.text
    assert "queued" in response.text
    assert "games.txt" in response.text


def test_job_detail_rejects_log_path_outside_jobs_dir(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    app.state.data_dir = tmp_path / "data"
    client = TestClient(app, raise_server_exceptions=False)

    _login(client)
    library_id = int(_create_library(client))

    conn = connect_db(str(db_path))
    try:
        conn.execute(
            """
            insert into dataset (library_id, filename, storage_path, size_bytes, created_at)
            values (?, ?, ?, ?, ?)
            """,
            (library_id, "games.txt", "uploads/1/games.txt", 4, "2026-02-02T00:00:00+00:00"),
        )
        dataset_id = conn.execute("select last_insert_rowid()").fetchone()[0]
        conn.execute(
            """
            insert into job (
                library_id,
                dataset_id,
                job_type,
                status,
                log_path,
                error,
                created_at,
                updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                library_id,
                dataset_id,
                "build",
                "queued",
                "/tmp/evil.log",
                None,
                "2026-02-02T00:00:00+00:00",
                "2026-02-02T00:00:00+00:00",
            ),
        )
        job_id = conn.execute("select last_insert_rowid()").fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    response = client.get(f"/jobs/{job_id}", follow_redirects=False)

    assert response.status_code == 404


def test_upload_cleans_file_when_job_create_fails(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    app.state.data_dir = tmp_path / "data"
    client = TestClient(app, raise_server_exceptions=False)

    _login(client)
    library_id = _create_library(client)
    csrf_token = _csrf_token(client)

    def _boom(*_args, **_kwargs):
        raise sqlite3.IntegrityError("boom")

    monkeypatch.setattr("game_web.services.job_service.create_job", _boom)

    response = client.post(
        f"/libraries/{library_id}/datasets/upload",
        data={"csrf_token": csrf_token},
        files={"file": ("games.txt", b"A\nB\n")},
        follow_redirects=False,
    )

    assert response.status_code == 500
    upload_path = Path(app.state.data_dir) / "uploads" / str(library_id) / "games.txt"
    assert not upload_path.exists()


def test_upload_rejects_when_payload_exceeds_limit(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    app.state.data_dir = tmp_path / "data"
    client = TestClient(app, raise_server_exceptions=False)

    _login(client)
    library_id = _create_library(client)
    csrf_token = _csrf_token(client)

    monkeypatch.setattr("game_web.services.dataset_service.UPLOAD_MAX_BYTES", 5)

    response = client.post(
        f"/libraries/{library_id}/datasets/upload",
        data={"csrf_token": csrf_token},
        files={"file": ("games.txt", b"ABCDEF")},
        follow_redirects=False,
    )

    assert response.status_code == 413


def test_job_detail_rejects_log_path_directory(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    app.state.data_dir = tmp_path / "data"
    client = TestClient(app)

    _login(client)
    library_id = int(_create_library(client))
    logs_dir = Path(app.state.data_dir) / "logs" / "jobs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    conn = connect_db(str(db_path))
    try:
        conn.execute(
            """
            insert into dataset (library_id, filename, storage_path, size_bytes, created_at)
            values (?, ?, ?, ?, ?)
            """,
            (library_id, "games.txt", "uploads/1/games.txt", 4, "2026-02-02T00:00:00+00:00"),
        )
        dataset_id = conn.execute("select last_insert_rowid()").fetchone()[0]
        conn.execute(
            """
            insert into job (
                library_id,
                dataset_id,
                job_type,
                status,
                log_path,
                error,
                created_at,
                updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                library_id,
                dataset_id,
                "build",
                "queued",
                "logs/jobs",
                None,
                "2026-02-02T00:00:00+00:00",
                "2026-02-02T00:00:00+00:00",
            ),
        )
        job_id = conn.execute("select last_insert_rowid()").fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    response = client.get(f"/jobs/{job_id}", follow_redirects=False)

    assert response.status_code == 404


def test_job_detail_rejects_symlinked_jobs_dir(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    app.state.data_dir = tmp_path / "data"
    client = TestClient(app)

    _login(client)
    library_id = int(_create_library(client))
    jobs_dir = Path(app.state.data_dir) / "logs" / "jobs"
    jobs_dir.parent.mkdir(parents=True, exist_ok=True)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    jobs_dir.symlink_to(outside_dir, target_is_directory=True)

    conn = connect_db(str(db_path))
    try:
        conn.execute(
            """
            insert into dataset (library_id, filename, storage_path, size_bytes, created_at)
            values (?, ?, ?, ?, ?)
            """,
            (library_id, "games.txt", "uploads/1/games.txt", 4, "2026-02-02T00:00:00+00:00"),
        )
        dataset_id = conn.execute("select last_insert_rowid()").fetchone()[0]
        conn.execute(
            """
            insert into job (
                library_id,
                dataset_id,
                job_type,
                status,
                log_path,
                error,
                created_at,
                updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                library_id,
                dataset_id,
                "build",
                "queued",
                "logs/jobs/job-1.log",
                None,
                "2026-02-02T00:00:00+00:00",
                "2026-02-02T00:00:00+00:00",
            ),
        )
        job_id = conn.execute("select last_insert_rowid()").fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    response = client.get(f"/jobs/{job_id}", follow_redirects=False)

    assert response.status_code == 404


def test_run_jobs_returns_202(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app, raise_server_exceptions=False)

    _login(client)
    _create_library(client)

    def _no_op(*_args, **_kwargs):
        return None

    monkeypatch.setattr("game_web.services.job_runner.JobRunner.run_next", _no_op)
    csrf_token = _csrf_token(client)
    response = client.post(
        "/jobs/run",
        data={"csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 202


def test_run_jobs_requires_csrf_token(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app, raise_server_exceptions=False)

    _login(client)
    _create_library(client)

    def _no_op(*_args, **_kwargs):
        return None

    monkeypatch.setattr("game_web.services.job_runner.JobRunner.run_next", _no_op)
    response = client.post("/jobs/run", follow_redirects=False)

    assert response.status_code == 403
