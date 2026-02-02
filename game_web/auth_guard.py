import datetime
from typing import NoReturn, cast

from fastapi import HTTPException, Request

from .db import connect_db


def _reject() -> NoReturn:
    raise HTTPException(status_code=401)


def require_login(request: Request) -> str:
    session_id = request.cookies.get("session")
    if session_id is None:
        _reject()
    session_id = cast(str, session_id)

    conn = connect_db(request.app.state.db_path)
    try:
        cur = conn.execute(
            "select id, expires_at from session where id = ?",
            (session_id,),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if row is None:
        _reject()
    row = cast(tuple, row)

    expires_at = None
    try:
        expires_at = datetime.datetime.fromisoformat(row[1])
    except (TypeError, ValueError):
        pass

    if expires_at is None:
        _reject()
    expires_at = cast(datetime.datetime, expires_at)

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)

    now = datetime.datetime.now(datetime.timezone.utc)
    if expires_at <= now:
        _reject()

    return session_id
