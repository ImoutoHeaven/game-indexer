from datetime import datetime, timezone
from typing import Any

from game_web.jobs import write_log_line


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def create_job(
    conn: Any,
    library_id: int,
    dataset_id: int,
    job_type: str,
    status: str = "queued",
    log_path: str | None = None,
    error: str | None = None,
    commit: bool = True,
) -> int:
    timestamp = _timestamp()
    cur = conn.execute(
        """
        insert into job (
            library_id,
            dataset_id,
            job_type,
            status,
            log_path,
            error,
            created_at,
            updated_at
        )
        values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (library_id, dataset_id, job_type, status, log_path, error, timestamp, timestamp),
    )
    if commit:
        conn.commit()
    return cur.lastrowid


def list_jobs(conn: Any) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        select job.id,
            job.library_id,
            library.name,
            job.dataset_id,
            dataset.filename,
            job.job_type,
            job.status,
            job.log_path,
            job.error,
            job.created_at,
            job.updated_at
        from job
        join library on library.id = job.library_id
        join dataset on dataset.id = job.dataset_id
        order by job.id desc
        """
    )
    rows = cur.fetchall()
    return [
        {
            "id": row[0],
            "library_id": row[1],
            "library_name": row[2],
            "dataset_id": row[3],
            "dataset_filename": row[4],
            "job_type": row[5],
            "status": row[6],
            "log_path": row[7],
            "error": row[8],
            "created_at": row[9],
            "updated_at": row[10],
        }
        for row in rows
    ]


def get_job(conn: Any, job_id: int) -> dict[str, Any] | None:
    cur = conn.execute(
        """
        select job.id,
            job.library_id,
            library.name,
            job.dataset_id,
            dataset.filename,
            job.job_type,
            job.status,
            job.log_path,
            job.error,
            job.created_at,
            job.updated_at
        from job
        join library on library.id = job.library_id
        join dataset on dataset.id = job.dataset_id
        where job.id = ?
        """,
        (job_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "library_id": row[1],
        "library_name": row[2],
        "dataset_id": row[3],
        "dataset_filename": row[4],
        "job_type": row[5],
        "status": row[6],
        "log_path": row[7],
        "error": row[8],
        "created_at": row[9],
        "updated_at": row[10],
    }


def get_next_queued_job(conn: Any) -> dict[str, Any] | None:
    cur = conn.execute(
        "select id from job where status = ? order by id asc limit 1",
        ("queued",),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return get_job(conn, int(row[0]))


def update_job(
    conn: Any,
    job_id: int,
    *,
    status: str | None = None,
    log_path: str | None = None,
    error: str | None = None,
    commit: bool = True,
) -> None:
    timestamp = _timestamp()
    conn.execute(
        """
        update job
        set status = coalesce(?, status),
            log_path = coalesce(?, log_path),
            error = ?,
            updated_at = ?
        where id = ?
        """,
        (status, log_path, error, timestamp, job_id),
    )
    if commit:
        conn.commit()


def claim_job(
    conn: Any,
    job_id: int,
    *,
    status: str = "running",
    log_path: str | None = None,
    commit: bool = True,
) -> dict[str, Any] | None:
    timestamp = _timestamp()
    cur = conn.execute(
        """
        update job
        set status = ?,
            log_path = coalesce(?, log_path),
            updated_at = ?
        where id = ? and status = ?
        """,
        (status, log_path, timestamp, job_id, "queued"),
    )
    if cur.rowcount == 0:
        return None
    if commit:
        conn.commit()
    return get_job(conn, job_id)


def append_job_log(path: str, line: str) -> None:
    formatted = f"{_timestamp()} [INFO] {line}"
    write_log_line(path, formatted)
