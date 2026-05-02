import sqlite3
from pathlib import Path

import pytest

from game_web.db import connect_db, init_db
from game_web.services import dataset_service, job_service
from game_web.services.embedding_profile import get_active_profile
from game_web.services.library_service import create_library, delete_library, list_libraries


def test_list_libraries_empty(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(str(db_path))
    conn = sqlite3.connect(db_path)
    try:
        libraries = list_libraries(conn)
    finally:
        conn.close()

    assert libraries == []


def test_create_library_and_list(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(str(db_path))
    conn = sqlite3.connect(db_path)
    try:
        create_library(
            conn,
            name="Main Library",
            index_uid="main-index",
            description="Primary games library",
        )
        libraries = list_libraries(conn)
    finally:
        conn.close()

    assert len(libraries) == 1
    library = libraries[0]
    assert isinstance(library["id"], int)
    assert library["name"] == "Main Library"
    assert library["index_uid"] == "main-index"
    assert library["description"] == "Primary games library"
    assert isinstance(library["created_at"], str)
    assert isinstance(library["updated_at"], str)


def test_create_library_creates_canonical_default_active_profile(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(str(db_path))
    conn = connect_db(str(db_path))
    try:
        create_library(
            conn,
            name="Main Library",
            index_uid="main-index",
            description="Primary games library",
        )
        library_id = list_libraries(conn)[0]["id"]
        profile = get_active_profile(conn, library_id)
    finally:
        conn.close()

    assert profile["key"] == "bge_m3"
    assert profile["model_name"] == "BAAI/bge-m3"
    assert profile["use_fp16"] == 0
    assert profile["max_length"] == 128
    assert profile["variant"] == "raw"
    assert profile["enabled"] == 1


def test_delete_library_removes_owned_files_but_not_remote_index(tmp_path):
    db_path = tmp_path / "app.db"
    data_dir = tmp_path / "data"
    init_db(str(db_path))
    conn = connect_db(str(db_path))
    try:
        create_library(
            conn,
            name="Main Library",
            index_uid="main-index",
            description="Primary games library",
        )
        library_id = list_libraries(conn)[0]["id"]
        dataset = dataset_service.create_dataset(
            conn,
            data_dir=data_dir,
            library_id=library_id,
            filename="games.txt",
            content=b"A\n",
        )
        job_id = job_service.create_job(
            conn,
            library_id=library_id,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="queued",
            log_path=f"logs/jobs/job-{dataset['id']}.log",
        )
        upload_path = data_dir / f"uploads/{library_id}/games.txt"
        log_path = data_dir / f"logs/jobs/job-{job_id}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("queued")

        deleted = delete_library(conn, library_id=library_id, data_dir=data_dir)
        libraries = list_libraries(conn)
        dataset_count = conn.execute(
            "select count(*) from dataset where library_id = ?",
            (library_id,),
        ).fetchone()[0]
        job_count = conn.execute(
            "select count(*) from job where library_id = ?",
            (library_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    assert deleted is True
    assert libraries == []
    assert dataset_count == 0
    assert job_count == 0
    assert not upload_path.exists()
    assert not log_path.exists()


def test_delete_library_restores_owned_files_when_a_later_delete_fails(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    data_dir = tmp_path / "data"
    init_db(str(db_path))
    conn = connect_db(str(db_path))
    try:
        create_library(
            conn,
            name="Main Library",
            index_uid="main-index",
            description="Primary games library",
        )
        library_id = list_libraries(conn)[0]["id"]
        dataset_service.create_dataset(
            conn,
            data_dir=data_dir,
            library_id=library_id,
            filename="first.txt",
            content=b"A\n",
        )
        dataset_service.create_dataset(
            conn,
            data_dir=data_dir,
            library_id=library_id,
            filename="second.txt",
            content=b"B\n",
        )

        first_path = (data_dir / f"uploads/{library_id}/first.txt").resolve()
        second_path = (data_dir / f"uploads/{library_id}/second.txt").resolve()
        original_unlink = Path.unlink

        def _boom(self: Path, *args, **kwargs):
            if self.resolve() == second_path:
                raise OSError("unlink failed")
            return original_unlink(self, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", _boom)

        with pytest.raises(OSError, match="unlink failed"):
            delete_library(conn, library_id=library_id, data_dir=data_dir)

        libraries = list_libraries(conn)
        dataset_count = conn.execute(
            "select count(*) from dataset where library_id = ?",
            (library_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    assert len(libraries) == 1
    assert dataset_count == 2
    assert first_path.exists()
    assert second_path.exists()
