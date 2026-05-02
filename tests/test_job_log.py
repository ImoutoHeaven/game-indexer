from datetime import datetime

from fastapi.testclient import TestClient

from game_web.app import create_app
from game_web.db import connect_db
from game_web.jobs import write_log_line
from game_web.services.embedding_profile import add_profile, list_profiles
from game_web.services import dataset_service, job_service, library_service
from game_web.services.job_service import append_job_log
from game_web.services.settings_service import set_setting


class FakeHealthyClient:
    def __init__(self, _url: str, _api_key: str | None):
        pass

    def health(self) -> dict[str, str]:
        return {"status": "available"}


def test_write_log_line(tmp_path):
    log_path = tmp_path / "job.log"
    write_log_line(str(log_path), "hello")
    assert log_path.read_text().strip() == "hello"


def test_write_log_line_appends_multiple_lines(tmp_path):
    log_path = tmp_path / "job.log"
    write_log_line(str(log_path), "hello")
    write_log_line(str(log_path), "world")
    assert log_path.read_text().splitlines() == ["hello", "world"]


def test_write_log_line_normalizes_newlines(tmp_path):
    log_path = tmp_path / "job.log"
    write_log_line(str(log_path), "hello\nworld")
    assert log_path.read_text().strip() == "hello world"


def test_append_job_log_includes_timestamp_level_and_message(tmp_path):
    log_path = tmp_path / "job.log"
    append_job_log(str(log_path), "hello\nworld")
    line = log_path.read_text().strip()
    assert "[INFO]" in line
    assert "hello world" in line
    assert "\n" not in line
    timestamp = line.split(" ", 1)[0]
    datetime.fromisoformat(timestamp)


def test_job_detail_links_back_to_library_and_search_when_searchable(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    app.state.data_dir = tmp_path / "data"
    client = TestClient(app)

    monkeypatch.setattr(
        "game_web.services.meili_health_service.meilisearch.Client",
        FakeHealthyClient,
    )

    response = client.get("/setup", follow_redirects=False)
    assert response.status_code == 200
    csrf_token = client.cookies.get("csrf_token")
    assert csrf_token
    response = client.post(
        "/setup",
        data={"password": "secret123", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 302
    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 200
    csrf_token = client.cookies.get("csrf_token")
    assert csrf_token
    response = client.post(
        "/login",
        data={"password": "secret123", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 302

    conn = connect_db(str(db_path))
    try:
        set_setting(conn, "meili_url", "http://127.0.0.1:7700", commit=False)
        library_service.create_library(
            conn,
            name="Primary Library",
            index_uid="primary-index",
            description="Main games library",
        )
        library_id = 1
        dataset = dataset_service.create_dataset(
            conn,
            data_dir=app.state.data_dir,
            library_id=library_id,
            filename="games.txt",
            content=b"A\n",
            commit=False,
        )
        job_id = job_service.create_job(
            conn,
            library_id=library_id,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="done",
            commit=False,
        )
        conn.commit()
    finally:
        conn.close()

    response = client.get(f"/jobs/{job_id}", follow_redirects=False)

    assert response.status_code == 200
    assert f'href="/libraries/{library_id}"' in response.text
    assert 'href="/search' in response.text


def test_job_detail_persists_canonical_active_profile_from_legacy_seed(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    app.state.data_dir = tmp_path / "data"
    client = TestClient(app)

    monkeypatch.setattr(
        "game_web.services.meili_health_service.meilisearch.Client",
        FakeHealthyClient,
    )

    response = client.get("/setup", follow_redirects=False)
    assert response.status_code == 200
    csrf_token = client.cookies.get("csrf_token")
    assert csrf_token
    response = client.post(
        "/setup",
        data={"password": "secret123", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 302
    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 200
    csrf_token = client.cookies.get("csrf_token")
    assert csrf_token
    response = client.post(
        "/login",
        data={"password": "secret123", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 302

    conn = connect_db(str(db_path))
    try:
        set_setting(conn, "meili_url", "http://127.0.0.1:7700", commit=False)
        conn.execute(
            """
            insert into library (name, index_uid, description, created_at, updated_at)
            values (?, ?, ?, ?, ?)
            """,
            (
                "Legacy Library",
                "legacy-index",
                "Legacy games library",
                "2026-02-02T00:00:00+00:00",
                "2026-02-02T00:00:00+00:00",
            ),
        )
        library_id = int(conn.execute("select last_insert_rowid()").fetchone()[0])
        add_profile(
            conn,
            library_id=library_id,
            key="legacy",
            model_name="legacy-model",
            use_fp16=1,
            max_length=256,
            commit=False,
        )
        dataset = dataset_service.create_dataset(
            conn,
            data_dir=app.state.data_dir,
            library_id=library_id,
            filename="games.txt",
            content=b"A\n",
            commit=False,
        )
        job_id = job_service.create_job(
            conn,
            library_id=library_id,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="done",
            commit=False,
        )
        conn.commit()
    finally:
        conn.close()

    check_conn = connect_db(str(db_path))
    try:
        before_keys = sorted(profile["key"] for profile in list_profiles(check_conn, library_id))
    finally:
        check_conn.close()

    assert before_keys == ["legacy"]

    response = client.get(f"/jobs/{job_id}", follow_redirects=False)

    assert response.status_code == 200
    assert f'href="/search?library={library_id}"' in response.text

    check_conn = connect_db(str(db_path))
    try:
        after_keys = sorted(profile["key"] for profile in list_profiles(check_conn, library_id))
    finally:
        check_conn.close()

    assert after_keys == ["bge_m3", "legacy"]
