from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from game_web.db import connect_db
from game_web.runtime import resolve_data_dir, resolve_jobs_dir
from game_web.services import job_service

LogFn = Callable[[str], None]
ExecuteFn = Callable[[dict[str, Any], LogFn], None]


def _default_log_path(job_id: int, base_rel: Path) -> str:
    return str(base_rel / f"job-{job_id}.log")


def _coerce_log_path(candidate: str | None, job_id: int, base_rel: Path) -> str:
    if not candidate:
        return _default_log_path(job_id, base_rel)
    path = Path(candidate)
    if path.is_absolute() or ".." in path.parts:
        return _default_log_path(job_id, base_rel)
    base_parts = base_rel.parts
    if path.parts[: len(base_parts)] != base_parts:
        return _default_log_path(job_id, base_rel)
    if len(path.parts) <= len(base_parts):
        return _default_log_path(job_id, base_rel)
    return str(path)


def _default_execute(job: dict[str, Any], log: LogFn) -> None:
    log(f"build job {job['id']} for {job['dataset_filename']}")


class JobRunner:
    def __init__(
        self,
        *,
        db_path: str,
        data_dir: Path | str | None = None,
        execute_job: ExecuteFn | None = None,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        self._db_path = db_path
        self._data_dir = resolve_data_dir(data_dir, db_path)
        self._execute_job = execute_job or _default_execute
        self._executor = executor or ThreadPoolExecutor(max_workers=1)

    def run_next(self) -> int | None:
        job = None
        log_path = None
        base_dir = resolve_jobs_dir(self._data_dir)
        base_rel = base_dir.relative_to(self._data_dir)
        while True:
            conn = connect_db(self._db_path)
            try:
                job = job_service.get_next_queued_job(conn)
                if job is None:
                    return None
                job_id = int(job["id"])
                log_path = _coerce_log_path(job.get("log_path"), job_id, base_rel)
                job = job_service.claim_job(conn, job_id, log_path=log_path)
                if job is None:
                    continue
                log_path = job.get("log_path") or log_path
                break
            finally:
                conn.close()

        full_log_path = (self._data_dir / log_path).resolve()
        if full_log_path != base_dir and base_dir not in full_log_path.parents:
            log_path = _default_log_path(job_id, base_rel)
            full_log_path = (self._data_dir / log_path).resolve()
        try:
            full_log_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            conn = connect_db(self._db_path)
            try:
                job_service.update_job(
                    conn,
                    job_id,
                    status="failed",
                    error=str(exc),
                    log_path=log_path,
                )
            finally:
                conn.close()
            raise

        def log_line(message: str) -> None:
            job_service.append_job_log(str(full_log_path), message)

        try:
            future = self._executor.submit(self._execute_job, job, log_line)
        except Exception as exc:
            conn = connect_db(self._db_path)
            try:
                job_service.update_job(
                    conn,
                    job_id,
                    status="failed",
                    error=str(exc),
                    log_path=log_path,
                )
            finally:
                conn.close()
            raise
        try:
            future.result()
        except Exception as exc:
            try:
                log_line(f"Job failed: {exc}")
            except Exception:
                pass
            conn = connect_db(self._db_path)
            try:
                job_service.update_job(
                    conn,
                    job_id,
                    status="failed",
                    error=str(exc),
                    log_path=log_path,
                )
            finally:
                conn.close()
            raise

        conn = connect_db(self._db_path)
        try:
            job_service.update_job(
                conn,
                job_id,
                status="done",
                error=None,
                log_path=log_path,
            )
        finally:
            conn.close()
        return job_id

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True)
