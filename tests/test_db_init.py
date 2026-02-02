import sqlite3

from game_web.db import init_db


def test_init_db_creates_tables(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(str(db_path))
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("select name from sqlite_master where type='table'")
    tables = {row[0] for row in cur.fetchall()}
    assert "admin_user" in tables
    assert "library" in tables
    assert "session" in tables
