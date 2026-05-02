from game_web.db import connect_db, init_db
from game_web.services import dataset_service, job_service, library_service


def test_get_latest_dataset_for_library_returns_newest_dataset(tmp_path):
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
        library_id = library_service.list_libraries(conn)[0]["id"]
        dataset_service.create_dataset(
            conn,
            data_dir=data_dir,
            library_id=library_id,
            filename="games-1.txt",
            content=b"A\n",
        )
        dataset_service.create_dataset(
            conn,
            data_dir=data_dir,
            library_id=library_id,
            filename="games-2.txt",
            content=b"B\n",
        )

        latest = job_service.get_latest_dataset_for_library(conn, library_id)
    finally:
        conn.close()

    assert latest is not None
    assert latest["filename"] == "games-2.txt"


def test_get_latest_relevant_build_job_ignores_superseded(tmp_path):
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
        library_id = library_service.list_libraries(conn)[0]["id"]
        older_dataset = dataset_service.create_dataset(
            conn,
            data_dir=data_dir,
            library_id=library_id,
            filename="games-1.txt",
            content=b"A\n",
        )
        latest_dataset = dataset_service.create_dataset(
            conn,
            data_dir=data_dir,
            library_id=library_id,
            filename="games-2.txt",
            content=b"B\n",
        )
        job_service.create_job(
            conn,
            library_id=library_id,
            dataset_id=int(older_dataset["id"]),
            job_type="build",
            status="done",
        )
        job_service.create_job(
            conn,
            library_id=library_id,
            dataset_id=int(latest_dataset["id"]),
            job_type="build",
            status="superseded",
        )
        newest_job_id = job_service.create_job(
            conn,
            library_id=library_id,
            dataset_id=int(latest_dataset["id"]),
            job_type="build",
            status="queued",
        )

        job = job_service.get_latest_relevant_build_job(conn, library_id)
    finally:
        conn.close()

    assert job is not None
    assert job["status"] == "queued"
    assert job["id"] == newest_job_id


def test_supersede_queued_jobs_marks_older_library_jobs_superseded(tmp_path):
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
        library_service.create_library(
            conn,
            name="Secondary Library",
            index_uid="secondary-index",
            description="Backup games library",
        )
        libraries = library_service.list_libraries(conn)
        primary_library_id = libraries[0]["id"]
        secondary_library_id = libraries[1]["id"]
        primary_dataset = dataset_service.create_dataset(
            conn,
            data_dir=data_dir,
            library_id=primary_library_id,
            filename="games.txt",
            content=b"A\n",
        )
        secondary_dataset = dataset_service.create_dataset(
            conn,
            data_dir=data_dir,
            library_id=secondary_library_id,
            filename="other-games.txt",
            content=b"B\n",
        )
        oldest_job_id = job_service.create_job(
            conn,
            library_id=primary_library_id,
            dataset_id=int(primary_dataset["id"]),
            job_type="build",
            status="queued",
        )
        older_job_id = job_service.create_job(
            conn,
            library_id=primary_library_id,
            dataset_id=int(primary_dataset["id"]),
            job_type="build",
            status="queued",
        )
        newest_job_id = job_service.create_job(
            conn,
            library_id=primary_library_id,
            dataset_id=int(primary_dataset["id"]),
            job_type="build",
            status="queued",
        )
        other_library_job_id = job_service.create_job(
            conn,
            library_id=secondary_library_id,
            dataset_id=int(secondary_dataset["id"]),
            job_type="build",
            status="queued",
        )

        count = job_service.supersede_queued_jobs(conn, primary_library_id)
        oldest_job = job_service.get_job(conn, oldest_job_id)
        older_job = job_service.get_job(conn, older_job_id)
        newest_job = job_service.get_job(conn, newest_job_id)
        other_library_job = job_service.get_job(conn, other_library_job_id)
    finally:
        conn.close()

    assert count == 2
    assert oldest_job is not None
    assert oldest_job["status"] == "superseded"
    assert older_job is not None
    assert older_job["status"] == "superseded"
    assert newest_job is not None
    assert newest_job["status"] == "queued"
    assert other_library_job is not None
    assert other_library_job["status"] == "queued"


def test_claim_next_executable_job_blocks_queued_work_while_another_library_build_is_running(tmp_path):
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
        library_service.create_library(
            conn,
            name="Secondary Library",
            index_uid="secondary-index",
            description="Backup games library",
        )
        libraries = library_service.list_libraries(conn)
        primary_library_id = libraries[0]["id"]
        secondary_library_id = libraries[1]["id"]
        primary_dataset = dataset_service.create_dataset(
            conn,
            data_dir=data_dir,
            library_id=primary_library_id,
            filename="games-1.txt",
            content=b"A\n",
        )
        secondary_dataset = dataset_service.create_dataset(
            conn,
            data_dir=data_dir,
            library_id=secondary_library_id,
            filename="games-2.txt",
            content=b"B\n",
        )
        running_job_id = job_service.create_job(
            conn,
            library_id=primary_library_id,
            dataset_id=int(primary_dataset["id"]),
            job_type="build",
            status="running",
        )
        queued_job_id = job_service.create_job(
            conn,
            library_id=secondary_library_id,
            dataset_id=int(secondary_dataset["id"]),
            job_type="build",
            status="queued",
        )

        claimed = job_service.claim_next_executable_job(conn)
        running_job = job_service.get_job(conn, running_job_id)
        queued_job = job_service.get_job(conn, queued_job_id)
    finally:
        conn.close()

    assert claimed is None
    assert running_job is not None
    assert running_job["status"] == "running"
    assert queued_job is not None
    assert queued_job["status"] == "queued"
