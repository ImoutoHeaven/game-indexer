import datetime
from typing import Any


def add_profile(
    conn: Any,
    library_id: int,
    key: str,
    model_name: str,
    use_fp16: int = 0,
    max_length: int = 128,
    variant: str = "raw",
    enabled: int = 1,
    commit: bool = True,
) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    timestamp = now.isoformat()
    conn.execute(
        """
        insert into embedding_profile (
            library_id,
            key,
            model_name,
            use_fp16,
            max_length,
            variant,
            enabled,
            created_at
        )
        values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (library_id, key, model_name, use_fp16, max_length, variant, enabled, timestamp),
    )
    if commit:
        conn.commit()


def list_profiles(conn: Any, library_id: int) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        select id,
            library_id,
            key,
            model_name,
            use_fp16,
            max_length,
            variant,
            enabled,
            created_at
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
            "use_fp16": row[4],
            "max_length": row[5],
            "variant": row[6],
            "enabled": row[7],
            "created_at": row[8],
        }
        for row in rows
    ]
