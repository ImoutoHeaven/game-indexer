import pytest

from game_web.db import connect_db, init_db
from game_web.services.embedding_profile import (
    add_profile,
    get_active_profile,
    list_profiles,
    upsert_active_profile,
)
from game_web.services.library_service import create_library, list_libraries
from game_web.services.settings_service import set_setting


class _FailFinalProfileUpdateConn:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        normalized_sql = " ".join(sql.split())
        if normalized_sql.startswith(
            "update embedding_profile set model_name = ?, use_fp16 = ?, max_length = ?, variant = ?, enabled = ? where id = ?"
        ):
            raise RuntimeError("forced update failure")
        return self._conn.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def test_add_and_list_profiles(tmp_path):
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
        add_profile(conn, library_id=library_id, key="v_name", model_name="BAAI/bge-m3")
        profiles = list_profiles(conn, library_id=library_id)
    finally:
        conn.close()

    keys = {profile["key"] for profile in profiles}
    assert "bge_m3" in keys
    assert "v_name" in keys


def test_add_profile_commit_flag(tmp_path):
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
        add_profile(
            conn,
            library_id=library_id,
            key="v_name",
            model_name="BAAI/bge-m3",
            commit=False,
        )
        check_conn = connect_db(str(db_path))
        try:
            profiles = list_profiles(check_conn, library_id=library_id)
            assert len(profiles) == 1
            assert profiles[0]["key"] == "bge_m3"
        finally:
            check_conn.close()
        conn.commit()
        check_conn = connect_db(str(db_path))
        try:
            profiles = list_profiles(check_conn, library_id=library_id)
        finally:
            check_conn.close()
    finally:
        conn.close()

    keys = {profile["key"] for profile in profiles}
    assert "bge_m3" in keys
    assert "v_name" in keys


def test_get_active_profile_creates_canonical_bge_m3_row_from_legacy_profile(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(str(db_path))
    conn = connect_db(str(db_path))
    try:
        conn.execute(
            """
            insert into library (name, index_uid, description, created_at, updated_at)
            values (?, ?, ?, ?, ?)
            """,
            (
                "Main Library",
                "main-index",
                "Primary games library",
                "2026-02-02T00:00:00+00:00",
                "2026-02-02T00:00:00+00:00",
            ),
        )
        library_id = conn.execute("select last_insert_rowid()").fetchone()[0]
        add_profile(
            conn,
            library_id=library_id,
            key="legacy",
            model_name="legacy-model",
            use_fp16=1,
            max_length=256,
        )

        profile = get_active_profile(conn, library_id)
        profiles = list_profiles(conn, library_id=library_id)
    finally:
        conn.close()

    assert profile["key"] == "bge_m3"
    assert profile["model_name"] == "legacy-model"
    assert profile["variant"] == "raw"
    assert profile["enabled"] == 1
    assert len([item for item in profiles if item["key"] == "bge_m3"]) == 1


def test_upsert_active_profile_rejects_blank_model_name(tmp_path):
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

        try:
            upsert_active_profile(
                conn,
                library_id=library_id,
                model_name=" ",
                use_fp16=0,
                max_length=128,
            )
        except ValueError as exc:
            assert "model name" in str(exc).lower()
        else:
            raise AssertionError("ValueError not raised")
    finally:
        conn.close()


def test_upsert_active_profile_reports_material_change(tmp_path):
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

        changed = upsert_active_profile(
            conn,
            library_id=library_id,
            model_name="BAAI/bge-m3",
            use_fp16=1,
            max_length=256,
            commit=True,
        )
        profile = get_active_profile(conn, library_id)
    finally:
        conn.close()

    assert changed is True
    assert profile["key"] == "bge_m3"
    assert profile["model_name"] == "BAAI/bge-m3"
    assert profile["use_fp16"] == 1
    assert profile["max_length"] == 256


def test_get_active_profile_does_not_commit_unrelated_pending_writes(tmp_path):
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
        conn.execute(
            "update embedding_profile set variant = ?, enabled = ? where library_id = ? and key = ?",
            ("legacy", 0, library_id, "bge_m3"),
        )
        conn.commit()

        set_setting(conn, "meili_url", "http://127.0.0.1:7700", commit=False)
        profile = get_active_profile(conn, library_id)

        check_conn = connect_db(str(db_path))
        try:
            persisted_profile = list_profiles(check_conn, library_id=library_id)[0]
            persisted_setting = check_conn.execute(
                "select value from settings where key = ?",
                ("meili_url",),
            ).fetchone()
        finally:
            check_conn.close()

        conn.commit()

        committed_conn = connect_db(str(db_path))
        try:
            committed_profile = list_profiles(committed_conn, library_id=library_id)[0]
            committed_setting = committed_conn.execute(
                "select value from settings where key = ?",
                ("meili_url",),
            ).fetchone()
        finally:
            committed_conn.close()
    finally:
        conn.close()

    assert profile["variant"] == "raw"
    assert profile["enabled"] == 1
    assert persisted_profile["variant"] == "legacy"
    assert persisted_profile["enabled"] == 0
    assert persisted_setting is None
    assert committed_profile["variant"] == "raw"
    assert committed_profile["enabled"] == 1
    assert committed_setting == ("http://127.0.0.1:7700",)


def test_upsert_active_profile_does_not_commit_unrelated_pending_writes(tmp_path):
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
        conn.execute(
            """
            insert into dataset (library_id, filename, storage_path, size_bytes, created_at)
            values (?, ?, ?, ?, ?)
            """,
            (
                library_id,
                "games.txt",
                str(data_dir / "uploads/1/games.txt"),
                4,
                "2026-02-02T00:00:00+00:00",
            ),
        )
        set_setting(conn, "meili_url", "http://127.0.0.1:7700", commit=False)

        changed = upsert_active_profile(
            conn,
            library_id=library_id,
            model_name="BAAI/bge-m3-large",
            use_fp16=1,
            max_length=256,
        )

        check_conn = connect_db(str(db_path))
        try:
            dataset_count_before_commit = check_conn.execute(
                "select count(*) from dataset where library_id = ?",
                (library_id,),
            ).fetchone()[0]
            persisted_setting = check_conn.execute(
                "select value from settings where key = ?",
                ("meili_url",),
            ).fetchone()
            persisted_profile = list_profiles(check_conn, library_id=library_id)[0]
        finally:
            check_conn.close()

        conn.commit()

        committed_conn = connect_db(str(db_path))
        try:
            dataset_count_after_commit = committed_conn.execute(
                "select count(*) from dataset where library_id = ?",
                (library_id,),
            ).fetchone()[0]
            committed_setting = committed_conn.execute(
                "select value from settings where key = ?",
                ("meili_url",),
            ).fetchone()
            committed_profile = list_profiles(committed_conn, library_id=library_id)[0]
        finally:
            committed_conn.close()
    finally:
        conn.close()

    assert changed is True
    assert dataset_count_before_commit == 0
    assert persisted_setting is None
    assert persisted_profile["model_name"] == "BAAI/bge-m3"
    assert persisted_profile["use_fp16"] == 0
    assert persisted_profile["max_length"] == 128
    assert dataset_count_after_commit == 1
    assert committed_setting == ("http://127.0.0.1:7700",)
    assert committed_profile["model_name"] == "BAAI/bge-m3-large"
    assert committed_profile["use_fp16"] == 1
    assert committed_profile["max_length"] == 256


def test_upsert_active_profile_commit_true_is_atomic_when_final_update_fails(tmp_path):
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
        set_setting(conn, "reviewer_probe", "x", commit=False)

        failing_conn = _FailFinalProfileUpdateConn(conn)

        with pytest.raises(RuntimeError, match="forced update failure"):
            upsert_active_profile(
                failing_conn,
                library_id=library_id,
                model_name="BAAI/bge-m3-large",
                use_fp16=1,
                max_length=256,
                commit=True,
            )

        conn.rollback()

        check_conn = connect_db(str(db_path))
        try:
            persisted_setting_after_failure = check_conn.execute(
                "select value from settings where key = ?",
                ("reviewer_probe",),
            ).fetchone()
            persisted_profile_after_failure = list_profiles(
                check_conn,
                library_id=library_id,
            )[0]
        finally:
            check_conn.close()
    finally:
        conn.close()

    assert persisted_setting_after_failure is None
    assert persisted_profile_after_failure["model_name"] == "BAAI/bge-m3"
    assert persisted_profile_after_failure["use_fp16"] == 0
    assert persisted_profile_after_failure["max_length"] == 128
