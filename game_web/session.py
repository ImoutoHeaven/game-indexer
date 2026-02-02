import datetime
import uuid
from typing import Any


def create_session(conn: Any, user_id: int, ttl_hours: int = 24) -> str:
    session_id = uuid.uuid4().hex
    created_at = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    expires_at = created_at + datetime.timedelta(hours=ttl_hours)
    conn.execute(
        "insert into session (id, user_id, created_at, expires_at) values (?, ?, ?, ?)",
        (
            session_id,
            user_id,
            created_at.isoformat(),
            expires_at.isoformat(),
        ),
    )
    conn.commit()
    return session_id
