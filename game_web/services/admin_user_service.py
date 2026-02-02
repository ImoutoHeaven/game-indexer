from datetime import datetime, timezone
import sqlite3

from game_web.auth import hash_password, verify_password


def has_admin(conn) -> bool:
    cur = conn.execute("select count(*) from admin_user")
    row = cur.fetchone()
    return row is not None and row[0] > 0


def create_admin(conn, password: str) -> int | None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    hashed = hash_password(password)
    try:
        conn.execute(
            "insert into admin_user (username, password_hash, created_at) values (?, ?, ?)",
            ("admin", hashed, now),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return None
    row = conn.execute(
        "select id from admin_user where username = ?",
        ("admin",),
    ).fetchone()
    if not row:
        return None
    return row[0]


def verify_admin(conn, password: str) -> int | None:
    row = conn.execute(
        "select id, password_hash from admin_user where username = ?",
        ("admin",),
    ).fetchone()
    if not row:
        return None
    if not verify_password(password, row[1]):
        return None
    return row[0]
