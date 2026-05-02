import re
import sqlite3
from pathlib import Path

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


def test_upload_dataset_redirects_back_to_library_detail_with_queued_notice(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app, raise_server_exceptions=False)

    _login(client)
    _set_reachable_settings(db_path, monkeypatch)
    library_id = _create_library(client)
    csrf_token = _csrf_token(client)

    response = client.post(
        f"/libraries/{library_id}/datasets/upload",
        data={"csrf_token": csrf_token},
        files={"file": ("games.txt", b"A\nB\n")},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert response.request.url.path == f"/libraries/{library_id}"
    assert "Build job queued" in response.text


def test_library_detail_shows_recent_build_summary(tmp_path, monkeypatch):
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
            name="Primary Library",
            index_uid="primary-index",
            description="Main games library",
        )
        dataset = dataset_service.create_dataset(
            conn,
            data_dir=app.state.data_dir,
            library_id=1,
            filename="games.txt",
            content=b"A\n",
            commit=False,
        )
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
                1,
                int(dataset["id"]),
                "build",
                "queued",
                None,
                None,
                "2026-02-02T00:00:00+00:00",
                "2026-02-02T00:00:00+00:00",
            ),
        )
        job_id = conn.execute("select last_insert_rowid()").fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    response = client.get("/libraries/1", follow_redirects=False)

    assert response.status_code == 200
    assert "Recent Build" in response.text
    assert "queued" in response.text
    assert "2026-02-02T00:00:00+00:00" in response.text
    assert f'href="/jobs/{job_id}"' in response.text


def test_library_detail_uses_the_four_section_mva_layout(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    _login(client)
    _set_reachable_settings(db_path, monkeypatch)
    library_id = _create_library(client)

    response = client.get(f"/libraries/{library_id}", follow_redirects=False)

    assert response.status_code == 200
    assert "Status" in response.text
    assert "Search Configuration" in response.text
    assert "Dataset & Build" in response.text
    assert "Recent Build" in response.text


def test_library_detail_status_section_shows_readiness_message_and_next_step(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    _login(client)
    _set_reachable_settings(db_path, monkeypatch)
    library_id = _create_library(client)

    response = client.get(f"/libraries/{library_id}", follow_redirects=False)

    assert response.status_code == 200
    assert "Needs dataset" in response.text
    assert "No dataset uploaded yet" in response.text
    assert "Upload dataset" in response.text


def test_library_detail_invalid_search_config_submission_stays_inline(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    _login(client)
    _set_reachable_settings(db_path, monkeypatch)
    library_id = _create_library(client)

    response = client.post(
        f"/libraries/{library_id}/search-config",
        data={
            "model_name": " ",
            "use_fp16": "0",
            "max_length": "128",
            "csrf_token": _csrf_token(client),
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Search Configuration" in response.text


def test_library_detail_valid_search_config_submission_shows_notice(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    _login(client)
    _set_reachable_settings(db_path, monkeypatch)
    library_id = _create_library(client)

    response = client.post(
        f"/libraries/{library_id}/search-config",
        data={
            "model_name": "BAAI/bge-m3",
            "use_fp16": "0",
            "max_length": "128",
            "csrf_token": _csrf_token(client),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Search configuration saved" in response.text


def test_library_detail_failed_build_shows_error_summary(tmp_path, monkeypatch):
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
            name="Primary Library",
            index_uid="primary-index",
            description="Main games library",
        )
        dataset = dataset_service.create_dataset(
            conn,
            data_dir=app.state.data_dir,
            library_id=1,
            filename="games.txt",
            content=b"A\n",
            commit=False,
        )
        job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="failed",
            error="build exploded",
            commit=False,
        )
        conn.commit()
    finally:
        conn.close()

    response = client.get("/libraries/1", follow_redirects=False)

    assert response.status_code == 200
    assert "Recent Build" in response.text
    assert "failed" in response.text
    assert "build exploded" in response.text


def test_upload_success_shows_run_or_inspect_path(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app, raise_server_exceptions=False)

    _login(client)
    _set_reachable_settings(db_path, monkeypatch)
    library_id = _create_library(client)
    csrf_token = _csrf_token(client)

    response = client.post(
        f"/libraries/{library_id}/datasets/upload",
        data={"csrf_token": csrf_token},
        files={"file": ("games.txt", b"A\nB\n")},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Build job queued" in response.text
    assert "Run next queued job" in response.text or 'href="/jobs/' in response.text


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
    assert "Dataset & Build" in response.text
    assert "too large" in response.text.lower()


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


def test_run_next_job_redirects_back_with_started_notice(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    app.state.data_dir = tmp_path / "data"
    client = TestClient(app, raise_server_exceptions=False)

    _login(client)
    library_id = _create_library(client)

    conn = connect_db(str(db_path))
    try:
        dataset = dataset_service.create_dataset(
            conn,
            data_dir=app.state.data_dir,
            library_id=int(library_id),
            filename="games.txt",
            content=b"A\n",
            commit=False,
        )
        job_service.create_job(
            conn,
            library_id=int(library_id),
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="queued",
            commit=False,
        )
        conn.commit()
    finally:
        conn.close()

    run_calls = {"count": 0}

    def _run_claimed(self, _job):
        run_calls["count"] += 1
        return 123

    monkeypatch.setattr("game_web.services.job_runner.JobRunner.run_claimed", _run_claimed)
    csrf_token = _csrf_token(client)
    response = client.post(
        "/jobs/run",
        data={"csrf_token": csrf_token, "return_to": f"/libraries/{library_id}"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert response.request.url.path == f"/libraries/{library_id}"
    assert "Build started" in response.text
    assert run_calls["count"] >= 1


def test_run_next_job_without_queued_work_shows_clear_non_success_notice(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app, raise_server_exceptions=False)

    _login(client)
    _create_library(client)

    def _run_next(self):
        return None

    monkeypatch.setattr("game_web.services.job_runner.JobRunner.run_next", _run_next)
    csrf_token = _csrf_token(client)
    response = client.post(
        "/jobs/run",
        data={"csrf_token": csrf_token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert response.request.url.path == "/jobs"
    assert "No queued jobs" in response.text


def test_run_next_job_does_not_report_success_when_no_job_claims(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    app.state.data_dir = tmp_path / "data"
    client = TestClient(app, raise_server_exceptions=False)

    _login(client)
    library_id = _create_library(client)

    conn = connect_db(str(db_path))
    try:
        dataset = dataset_service.create_dataset(
            conn,
            data_dir=app.state.data_dir,
            library_id=int(library_id),
            filename="games.txt",
            content=b"A\n",
            commit=False,
        )
        job_service.create_job(
            conn,
            library_id=int(library_id),
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="queued",
            commit=False,
        )
        conn.commit()
    finally:
        conn.close()

    run_next_calls = {"count": 0}

    def _claim_next(self):
        return None

    def _run_next(self):
        run_next_calls["count"] += 1
        return None

    monkeypatch.setattr("game_web.services.job_runner.JobRunner.claim_next", _claim_next, raising=False)
    monkeypatch.setattr("game_web.services.job_runner.JobRunner.run_next", _run_next)

    response = client.post(
        "/jobs/run",
        data={"csrf_token": _csrf_token(client)},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert response.request.url.path == "/jobs"
    assert "Build did not start. Queued work is waiting for the running build to finish." in response.text
    assert "Build started" not in response.text
    assert run_next_calls["count"] == 0


def test_run_next_job_does_not_start_same_library_build_while_older_job_is_running(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    app.state.data_dir = tmp_path / "data"
    client = TestClient(app, raise_server_exceptions=False)

    _login(client)
    library_id = _create_library(client)

    conn = connect_db(str(db_path))
    try:
        older_dataset = dataset_service.create_dataset(
            conn,
            data_dir=app.state.data_dir,
            library_id=int(library_id),
            filename="games-v1.txt",
            content=b"A\n",
            commit=False,
        )
        older_job_id = job_service.create_job(
            conn,
            library_id=int(library_id),
            dataset_id=int(older_dataset["id"]),
            job_type="build",
            status="running",
            commit=False,
        )
        newer_dataset = dataset_service.create_dataset(
            conn,
            data_dir=app.state.data_dir,
            library_id=int(library_id),
            filename="games-v2.txt",
            content=b"B\n",
            commit=False,
        )
        newer_job_id = job_service.create_job(
            conn,
            library_id=int(library_id),
            dataset_id=int(newer_dataset["id"]),
            job_type="build",
            status="queued",
            commit=False,
        )
        conn.commit()
    finally:
        conn.close()

    start_calls = {"count": 0}

    class _Thread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            start_calls["count"] += 1

    monkeypatch.setattr("game_web.routes.jobs.Thread", _Thread)

    response = client.post(
        "/jobs/run",
        data={"csrf_token": _csrf_token(client)},
        follow_redirects=True,
    )

    conn = connect_db(str(db_path))
    try:
        older_job = job_service.get_job(conn, older_job_id)
        newer_job = job_service.get_job(conn, newer_job_id)
    finally:
        conn.close()

    assert response.status_code == 200
    assert response.request.url.path == "/jobs"
    assert "Build started" not in response.text
    assert "Build did not start. Queued work is waiting for the running build to finish." in response.text
    assert "No queued jobs" not in response.text
    assert start_calls["count"] == 0
    assert older_job is not None
    assert older_job["status"] == "running"
    assert newer_job is not None
    assert newer_job["status"] == "queued"
    assert "games-v2.txt" in response.text
    assert "queued" in response.text


def test_run_next_job_does_not_start_other_library_build_while_a_build_is_running(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    app.state.data_dir = tmp_path / "data"
    client = TestClient(app, raise_server_exceptions=False)

    _login(client)
    primary_library_id = _create_library(client)
    csrf_token = _csrf_token(client)
    response = client.post(
        "/libraries/create",
        data={
            "name": "Secondary Library",
            "index_uid": "secondary-index",
            "description": "Backup games library",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    conn = connect_db(str(db_path))
    try:
        secondary_library_id = conn.execute(
            "select id from library where index_uid = ?",
            ("secondary-index",),
        ).fetchone()[0]
        running_dataset = dataset_service.create_dataset(
            conn,
            data_dir=app.state.data_dir,
            library_id=int(primary_library_id),
            filename="games-v1.txt",
            content=b"A\n",
            commit=False,
        )
        running_job_id = job_service.create_job(
            conn,
            library_id=int(primary_library_id),
            dataset_id=int(running_dataset["id"]),
            job_type="build",
            status="running",
            commit=False,
        )
        queued_dataset = dataset_service.create_dataset(
            conn,
            data_dir=app.state.data_dir,
            library_id=int(secondary_library_id),
            filename="games-v2.txt",
            content=b"B\n",
            commit=False,
        )
        queued_job_id = job_service.create_job(
            conn,
            library_id=int(secondary_library_id),
            dataset_id=int(queued_dataset["id"]),
            job_type="build",
            status="queued",
            commit=False,
        )
        conn.commit()
    finally:
        conn.close()

    start_calls = {"count": 0}

    class _Thread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            start_calls["count"] += 1

    monkeypatch.setattr("game_web.routes.jobs.Thread", _Thread)

    response = client.post(
        "/jobs/run",
        data={"csrf_token": _csrf_token(client)},
        follow_redirects=True,
    )

    conn = connect_db(str(db_path))
    try:
        running_job = job_service.get_job(conn, running_job_id)
        queued_job = job_service.get_job(conn, queued_job_id)
    finally:
        conn.close()

    assert response.status_code == 200
    assert response.request.url.path == "/jobs"
    assert "Build started" not in response.text
    assert "Build did not start. Queued work is waiting for the running build to finish." in response.text
    assert "No queued jobs" not in response.text
    assert start_calls["count"] == 0
    assert running_job is not None
    assert running_job["status"] == "running"
    assert queued_job is not None
    assert queued_job["status"] == "queued"
    assert "Secondary Library" in response.text
    assert "games-v2.txt" in response.text
    assert "queued" in response.text


def test_run_next_job_start_failure_marks_claimed_job_failed_and_redirects(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    app.state.data_dir = tmp_path / "data"
    client = TestClient(app, raise_server_exceptions=False)

    _login(client)
    library_id = _create_library(client)

    conn = connect_db(str(db_path))
    try:
        dataset = dataset_service.create_dataset(
            conn,
            data_dir=app.state.data_dir,
            library_id=int(library_id),
            filename="games.txt",
            content=b"A\n",
            commit=False,
        )
        job_id = job_service.create_job(
            conn,
            library_id=int(library_id),
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="queued",
            commit=False,
        )
        conn.commit()
    finally:
        conn.close()

    class _BoomThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise RuntimeError("thread start failed")

    monkeypatch.setattr("game_web.routes.jobs.Thread", _BoomThread)

    response = client.post(
        "/jobs/run",
        data={"csrf_token": _csrf_token(client), "return_to": f"/libraries/{library_id}"},
        follow_redirects=True,
    )

    conn = connect_db(str(db_path))
    try:
        job = job_service.get_job(conn, job_id)
    finally:
        conn.close()

    assert response.status_code == 200
    assert response.request.url.path == f"/libraries/{library_id}"
    assert "Build did not start" in response.text
    assert "Build started" not in response.text
    assert job is not None
    assert job["status"] == "failed"
    assert job["error"] == "thread start failed"


def test_job_detail_shows_superseded_explanation(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    app.state.data_dir = tmp_path / "data"
    client = TestClient(app)

    _login(client)

    conn = connect_db(str(db_path))
    try:
        library_service.create_library(
            conn,
            name="Primary Library",
            index_uid="primary-index",
            description="Main games library",
        )
        dataset = dataset_service.create_dataset(
            conn,
            data_dir=app.state.data_dir,
            library_id=1,
            filename="games.txt",
            content=b"A\n",
            commit=False,
        )
        job_id = job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="superseded",
            commit=False,
        )
        conn.commit()
    finally:
        conn.close()

    response = client.get(f"/jobs/{job_id}", follow_redirects=False)

    assert response.status_code == 200
    assert "superseded" in response.text
    assert "newer build request replaced it" in response.text


def test_jobs_page_shows_superseded_explanation(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    app.state.data_dir = tmp_path / "data"
    client = TestClient(app)

    _login(client)

    conn = connect_db(str(db_path))
    try:
        library_service.create_library(
            conn,
            name="Primary Library",
            index_uid="primary-index",
            description="Main games library",
        )
        dataset = dataset_service.create_dataset(
            conn,
            data_dir=app.state.data_dir,
            library_id=1,
            filename="games.txt",
            content=b"A\n",
            commit=False,
        )
        job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="superseded",
            commit=False,
        )
        conn.commit()
    finally:
        conn.close()

    response = client.get("/jobs", follow_redirects=False)

    assert response.status_code == 200
    assert "superseded" in response.text
    assert "This job never ran because a newer build request replaced it before execution." in response.text


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
