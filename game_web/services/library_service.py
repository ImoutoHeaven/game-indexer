import datetime
from typing import Any

from game_web.services.embedding_profile import add_profile


def create_library(
    conn: Any,
    name: str,
    index_uid: str,
    description: str | None = None,
) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    timestamp = now.isoformat()
    cur = conn.execute(
        """
        insert into library (name, index_uid, description, created_at, updated_at)
        values (?, ?, ?, ?, ?)
        """,
        (name, index_uid, description, timestamp, timestamp),
    )
    library_id = cur.lastrowid
    add_profile(
        conn,
        library_id=library_id,
        key="default",
        model_name="default",
        use_fp16=0,
        max_length=128,
        variant="raw",
        enabled=1,
        commit=False,
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


def get_library(conn: Any, library_id: int) -> dict[str, Any] | None:
    cur = conn.execute(
        """
        select id, name, index_uid, description, created_at, updated_at
        from library
        where id = ?
        """,
        (library_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "index_uid": row[2],
        "description": row[3],
        "created_at": row[4],
        "updated_at": row[5],
    }


def delete_library(conn: Any, library_id: int) -> bool:
    cur = conn.execute("delete from library where id = ?", (library_id,))
    conn.commit()
    return cur.rowcount > 0
