import pytest

from game_web.db import connect_db, init_db
from game_web.services import dataset_service, job_service, library_service
from game_web.services.job_runner import JobRunner


@pytest.fixture(autouse=True)
def _stub_build_execution(monkeypatch):
    def _execute_build_job(*, db_path, data_dir, job, log):
        log(f"build job {job['id']} for {job['dataset_filename']}")

    monkeypatch.setattr("game_web.services.job_runner.execute_build_job", _execute_build_job)


def test_job_runner_executes_real_build_callback_and_marks_job_done(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    data_dir = tmp_path / "data"
    init_db(str(db_path))
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
            data_dir=data_dir,
            library_id=1,
            filename="games.txt",
            content=b"A\n",
        )
        job_id = job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="queued",
        )
    finally:
        conn.close()

    captured = {}

    def _execute_build_job(*, db_path, data_dir, job, log):
        captured["db_path"] = db_path
        captured["data_dir"] = data_dir
        captured["job_id"] = job["id"]
        log(f"building job {job['id']}")

    monkeypatch.setattr("game_web.services.job_runner.execute_build_job", _execute_build_job)

    runner = JobRunner(db_path=str(db_path), data_dir=data_dir)
    try:
        assert runner.run_next() == job_id
    finally:
        runner.shutdown()

    conn = connect_db(str(db_path))
    try:
        job = job_service.get_job(conn, job_id)
    finally:
        conn.close()

    assert captured["db_path"] == str(db_path)
    assert captured["data_dir"] == data_dir
    assert captured["job_id"] == job_id
    assert job is not None
    assert job["status"] == "done"


def test_job_runner_marks_job_failed_when_build_wait_raises(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    data_dir = tmp_path / "data"
    init_db(str(db_path))
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
            data_dir=data_dir,
            library_id=1,
            filename="games.txt",
            content=b"A\n",
        )
        job_id = job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="queued",
        )
    finally:
        conn.close()

    def _wait_failure(*, db_path, data_dir, job, log):
        log("submitted build task")
        raise RuntimeError("task wait failed")

    monkeypatch.setattr("game_web.services.job_runner.execute_build_job", _wait_failure)

    runner = JobRunner(db_path=str(db_path), data_dir=data_dir)
    try:
        with pytest.raises(RuntimeError, match="task wait failed"):
            runner.run_next()
    finally:
        runner.shutdown()

    conn = connect_db(str(db_path))
    try:
        job = job_service.get_job(conn, job_id)
    finally:
        conn.close()

    assert job is not None
    assert job["status"] == "failed"


def test_job_runner_skips_superseded_jobs_and_runs_next_queued_job(tmp_path):
    db_path = tmp_path / "app.db"
    data_dir = tmp_path / "data"
    init_db(str(db_path))
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
            data_dir=data_dir,
            library_id=1,
            filename="games.txt",
            content=b"A\n",
        )
        older_job_id = job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="queued",
        )
        newest_job_id = job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="queued",
        )
    finally:
        conn.close()

    runner = JobRunner(db_path=str(db_path), data_dir=data_dir)
    try:
        assert runner.run_next() == newest_job_id
    finally:
        runner.shutdown()

    conn = connect_db(str(db_path))
    try:
        older_job = job_service.get_job(conn, older_job_id)
        newest_job = job_service.get_job(conn, newest_job_id)
    finally:
        conn.close()

    assert older_job is not None
    assert older_job["status"] == "superseded"
    assert newest_job is not None
    assert newest_job["status"] == "done"


def test_job_runner_marks_job_failed_when_execute_build_job_raises(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    data_dir = tmp_path / "data"
    init_db(str(db_path))
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
            data_dir=data_dir,
            library_id=1,
            filename="games.txt",
            content=b"A\n",
        )
        job_id = job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="queued",
        )
    finally:
        conn.close()

    def _boom(*, db_path, data_dir, job, log):
        raise RuntimeError("boom")

    monkeypatch.setattr("game_web.services.job_runner.execute_build_job", _boom)

    runner = JobRunner(db_path=str(db_path), data_dir=data_dir)
    try:
        with pytest.raises(RuntimeError):
            runner.run_next()
    finally:
        runner.shutdown()

    conn = connect_db(str(db_path))
    try:
        job = job_service.get_job(conn, job_id)
    finally:
        conn.close()

    assert job is not None
    assert job["status"] == "failed"


def test_job_runner_marks_queued_job_done_and_writes_log(tmp_path):
    db_path = tmp_path / "app.db"
    data_dir = tmp_path / "data"
    init_db(str(db_path))
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
            data_dir=data_dir,
            library_id=1,
            filename="games.txt",
            content=b"A\n",
        )
        job_id = job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="queued",
        )
    finally:
        conn.close()

    calls = {"count": 0}

    def _execute(*, db_path, data_dir, job, log):
        calls["count"] += 1
        log(f"building job {job['id']}")

    runner = JobRunner(db_path=str(db_path), data_dir=data_dir, execute_job=_execute)
    try:
        assert runner.run_next() == job_id
    finally:
        runner.shutdown()

    conn = connect_db(str(db_path))
    try:
        job = job_service.get_job(conn, job_id)
    finally:
        conn.close()

    assert job is not None
    assert job["status"] == "done"
    assert calls["count"] == 1
    assert job["log_path"]
    log_path = data_dir / job["log_path"]
    log_text = log_path.read_text()
    assert "[INFO]" in log_text
    assert "building job" in log_text


def test_job_runner_overrides_absolute_log_path(tmp_path):
    db_path = tmp_path / "app.db"
    data_dir = tmp_path / "data"
    init_db(str(db_path))
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
            data_dir=data_dir,
            library_id=1,
            filename="games.txt",
            content=b"A\n",
        )
        job_id = job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="queued",
            log_path="/tmp/evil.log",
        )
    finally:
        conn.close()

    runner = JobRunner(db_path=str(db_path), data_dir=data_dir)
    try:
        assert runner.run_next() == job_id
    finally:
        runner.shutdown()

    conn = connect_db(str(db_path))
    try:
        job = job_service.get_job(conn, job_id)
    finally:
        conn.close()

    assert job is not None
    assert job["log_path"] == f"logs/jobs/job-{job_id}.log"
    log_path = data_dir / job["log_path"]
    assert log_path.exists()


def test_job_runner_rewrites_log_path_outside_jobs_dir(tmp_path):
    db_path = tmp_path / "app.db"
    data_dir = tmp_path / "data"
    init_db(str(db_path))
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
            data_dir=data_dir,
            library_id=1,
            filename="games.txt",
            content=b"A\n",
        )
        job_id = job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="queued",
            log_path="logs/other/x.log",
        )
    finally:
        conn.close()

    runner = JobRunner(db_path=str(db_path), data_dir=data_dir)
    try:
        assert runner.run_next() == job_id
    finally:
        runner.shutdown()

    conn = connect_db(str(db_path))
    try:
        job = job_service.get_job(conn, job_id)
    finally:
        conn.close()

    assert job is not None
    assert job["log_path"] == f"logs/jobs/job-{job_id}.log"


def test_job_runner_rewrites_log_path_directory(tmp_path):
    db_path = tmp_path / "app.db"
    data_dir = tmp_path / "data"
    init_db(str(db_path))
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
            data_dir=data_dir,
            library_id=1,
            filename="games.txt",
            content=b"A\n",
        )
        job_id = job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="queued",
            log_path="logs/jobs",
        )
    finally:
        conn.close()

    runner = JobRunner(db_path=str(db_path), data_dir=data_dir)
    try:
        assert runner.run_next() == job_id
    finally:
        runner.shutdown()

    conn = connect_db(str(db_path))
    try:
        job = job_service.get_job(conn, job_id)
    finally:
        conn.close()

    assert job is not None
    assert job["log_path"] == f"logs/jobs/job-{job_id}.log"


def test_job_runner_rewrites_log_path_when_jobs_dir_symlinked(tmp_path):
    db_path = tmp_path / "app.db"
    data_dir = tmp_path / "data"
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    jobs_dir = data_dir / "logs" / "jobs"
    jobs_dir.parent.mkdir(parents=True, exist_ok=True)
    jobs_dir.symlink_to(outside_dir, target_is_directory=True)
    init_db(str(db_path))
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
            data_dir=data_dir,
            library_id=1,
            filename="games.txt",
            content=b"A\n",
        )
        job_id = job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="queued",
            log_path=f"logs/jobs/job-{dataset['id']}.log",
        )
    finally:
        conn.close()

    runner = JobRunner(db_path=str(db_path), data_dir=data_dir)
    try:
        assert runner.run_next() == job_id
    finally:
        runner.shutdown()

    conn = connect_db(str(db_path))
    try:
        job = job_service.get_job(conn, job_id)
    finally:
        conn.close()

    assert job is not None
    assert job["log_path"] == f"logs_safe/jobs/job-{job_id}.log"


def test_job_runner_updates_status_when_log_append_fails(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    data_dir = tmp_path / "data"
    init_db(str(db_path))
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
            data_dir=data_dir,
            library_id=1,
            filename="games.txt",
            content=b"A\n",
        )
        job_id = job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="queued",
        )
    finally:
        conn.close()

    def _execute(*, db_path, data_dir, job, log):
        raise RuntimeError("boom")

    def _boom(*_args, **_kwargs):
        raise OSError("append failed")

    monkeypatch.setattr("game_web.services.job_service.append_job_log", _boom)

    runner = JobRunner(db_path=str(db_path), data_dir=data_dir, execute_job=_execute)
    try:
        try:
            runner.run_next()
        except RuntimeError:
            pass
    finally:
        runner.shutdown()

    conn = connect_db(str(db_path))
    try:
        job = job_service.get_job(conn, job_id)
    finally:
        conn.close()

    assert job is not None
    assert job["status"] == "failed"


def test_job_runner_updates_status_when_submit_fails(tmp_path):
    db_path = tmp_path / "app.db"
    data_dir = tmp_path / "data"
    init_db(str(db_path))
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
            data_dir=data_dir,
            library_id=1,
            filename="games.txt",
            content=b"A\n",
        )
        job_id = job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="queued",
        )
    finally:
        conn.close()

    class _BoomExecutor:
        def submit(self, *_args, **_kwargs):
            raise RuntimeError("submit failed")

        def shutdown(self, wait=True):
            pass

    runner = JobRunner(
        db_path=str(db_path),
        data_dir=data_dir,
        executor=_BoomExecutor(),  # type: ignore[arg-type]
    )
    try:
        try:
            runner.run_next()
        except RuntimeError:
            pass
    finally:
        runner.shutdown()

    conn = connect_db(str(db_path))
    try:
        job = job_service.get_job(conn, job_id)
    finally:
        conn.close()

    assert job is not None
    assert job["status"] == "failed"


def test_job_runner_updates_status_when_mkdir_fails(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    data_dir = tmp_path / "data"
    init_db(str(db_path))
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
            data_dir=data_dir,
            library_id=1,
            filename="games.txt",
            content=b"A\n",
        )
        job_id = job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="queued",
        )
    finally:
        conn.close()

    def _boom(*_args, **_kwargs):
        raise OSError("mkdir failed")

    monkeypatch.setattr("pathlib.Path.mkdir", _boom)

    runner = JobRunner(db_path=str(db_path), data_dir=data_dir)
    try:
        try:
            runner.run_next()
        except OSError:
            pass
    finally:
        runner.shutdown()

    conn = connect_db(str(db_path))
    try:
        job = job_service.get_job(conn, job_id)
    finally:
        conn.close()

    assert job is not None
    assert job["status"] == "failed"


def test_claim_job_returns_none_when_status_not_queued(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(str(db_path))
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
            data_dir=tmp_path / "data",
            library_id=1,
            filename="games.txt",
            content=b"A\n",
        )
        job_id = job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="done",
        )
    finally:
        conn.close()

    conn = connect_db(str(db_path))
    try:
        claimed = job_service.claim_job(conn, job_id)
    finally:
        conn.close()

    assert claimed is None
