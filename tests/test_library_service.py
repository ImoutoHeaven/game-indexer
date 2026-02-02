import sqlite3

from game_web.db import init_db
from game_web.services.library_service import create_library, list_libraries


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
