from game_web.db import connect_db, init_db
from game_web.services.embedding_profile import add_profile, list_profiles
from game_web.services.library_service import create_library, list_libraries


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
    assert "default" in keys
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
            assert profiles[0]["key"] == "default"
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
    assert "default" in keys
    assert "v_name" in keys
