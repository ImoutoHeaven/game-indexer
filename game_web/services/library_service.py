import datetime
from typing import Any


def create_library(
    conn: Any,
    name: str,
    index_uid: str,
    description: str | None = None,
) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    timestamp = now.isoformat()
    conn.execute(
        """
        insert into library (name, index_uid, description, created_at, updated_at)
        values (?, ?, ?, ?, ?)
        """,
        (name, index_uid, description, timestamp, timestamp),
    )
    conn.commit()


def list_libraries(conn: Any) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        select id, name, index_uid, description, created_at, updated_at
        from library
        order by id
        """,
    )
    rows = cur.fetchall()
    return [
        {
            "id": row[0],
            "name": row[1],
            "index_uid": row[2],
            "description": row[3],
            "created_at": row[4],
            "updated_at": row[5],
        }
        for row in rows
    ]
