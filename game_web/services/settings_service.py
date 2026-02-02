import datetime
from typing import Any


def get_setting(conn: Any, key: str) -> str | None:
    cur = conn.execute("select value from settings where key = ?", (key,))
    row = cur.fetchone()
    if row is None:
        return None
    return row[0]


def set_setting(conn: Any, key: str, value: str, commit: bool = True) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    timestamp = now.isoformat()
    cur = conn.execute("select 1 from settings where key = ?", (key,))
    if cur.fetchone() is None:
        conn.execute(
            "insert into settings (key, value, updated_at) values (?, ?, ?)",
            (key, value, timestamp),
        )
    else:
        conn.execute(
            "update settings set value = ?, updated_at = ? where key = ?",
            (value, timestamp, key),
        )
    if commit:
        conn.commit()


def clear_setting(conn: Any, key: str, commit: bool = True) -> None:
    conn.execute("delete from settings where key = ?", (key,))
    if commit:
        conn.commit()
