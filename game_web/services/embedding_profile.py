import datetime
from typing import Any


def add_profile(
    conn: Any,
    library_id: int,
    key: str,
    model_name: str,
    commit: bool = True,
) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    timestamp = now.isoformat()
    conn.execute(
        """
        insert into embedding_profile (library_id, key, model_name, created_at)
        values (?, ?, ?, ?)
        """,
        (library_id, key, model_name, timestamp),
    )
    if commit:
        conn.commit()


def list_profiles(conn: Any, library_id: int) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        select id, library_id, key, model_name, created_at
        from embedding_profile
        where library_id = ?
        order by id
        """,
        (library_id,),
    )
    rows = cur.fetchall()
    return [
        {
            "id": row[0],
            "library_id": row[1],
            "key": row[2],
            "model_name": row[3],
            "created_at": row[4],
        }
        for row in rows
    ]
