import datetime
from pathlib import Path
from typing import Any

from game_web.services.embedding_profile import (
    ACTIVE_PROFILE_ENABLED,
    ACTIVE_PROFILE_KEY,
    ACTIVE_PROFILE_VARIANT,
    DEFAULT_MAX_LENGTH,
    DEFAULT_MODEL_NAME,
    DEFAULT_USE_FP16,
    add_profile,
)


def _safe_owned_path(data_dir: Path, relative_path: str | None) -> Path | None:
    if not relative_path:
        return None
    candidate = (data_dir / relative_path).resolve()
    if candidate == data_dir or data_dir not in candidate.parents:
        return None
    return candidate


def _snapshot_owned_files(data_dir: Path, relative_paths: list[str | None]) -> dict[Path, bytes]:
    backups: dict[Path, bytes] = {}
    for relative_path in relative_paths:
        candidate = _safe_owned_path(data_dir, relative_path)
        if candidate is None or not candidate.exists() or not candidate.is_file():
            continue
        backups[candidate] = candidate.read_bytes()
    return backups


def _restore_owned_files(backups: dict[Path, bytes]) -> None:
    for candidate, content in backups.items():
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_bytes(content)


def _delete_owned_files(backups: dict[Path, bytes]) -> None:
    try:
        for candidate in backups:
            candidate.unlink()
    except OSError:
        _restore_owned_files(backups)
        raise


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
        key=ACTIVE_PROFILE_KEY,
        model_name=DEFAULT_MODEL_NAME,
        use_fp16=DEFAULT_USE_FP16,
        max_length=DEFAULT_MAX_LENGTH,
        variant=ACTIVE_PROFILE_VARIANT,
        enabled=ACTIVE_PROFILE_ENABLED,
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


def delete_library(conn: Any, library_id: int, *, data_dir: Path | None = None) -> bool:
    upload_paths: list[str | None] = []
    log_paths: list[str | None] = []
    owned_file_backups: dict[Path, bytes] = {}
    if data_dir is not None:
        upload_paths = [
            row[0]
            for row in conn.execute(
                "select storage_path from dataset where library_id = ?",
                (library_id,),
            ).fetchall()
        ]
        log_paths = [
            row[0]
            for row in conn.execute(
                "select log_path from job where library_id = ?",
                (library_id,),
            ).fetchall()
        ]
        owned_file_backups = _snapshot_owned_files(data_dir, upload_paths + log_paths)
        _delete_owned_files(owned_file_backups)

    try:
        cur = conn.execute("delete from library where id = ?", (library_id,))
        if cur.rowcount == 0:
            conn.rollback()
            if owned_file_backups:
                _restore_owned_files(owned_file_backups)
            return False
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        if owned_file_backups:
            _restore_owned_files(owned_file_backups)
        raise
