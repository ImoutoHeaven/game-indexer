from pathlib import Path
from threading import Thread
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from game_web.auth_guard import require_login_redirect
from game_web.csrf import require_csrf
from game_web.db import connect_db
from game_web.routes.library import _active_profile_is_valid, _get_meili_health_for_request
from game_web.runtime import resolve_data_dir, resolve_jobs_dir
from game_web.services.embedding_profile import get_active_profile
from game_web.services.job_runner import JobRunner
from game_web.services.job_service import get_latest_relevant_build_job, has_queued_build_jobs
from game_web.services.library_status import derive_library_status
from game_web.services.library_service import get_library
from game_web.services.job_service import get_job, list_jobs

router = APIRouter()


def _redirect_with_message(path: str, *, notice: str | None = None, error: str | None = None) -> RedirectResponse:
    params = {}
    if notice:
        params["notice"] = notice
    if error:
        params["error"] = error
    if params:
        path = f"{path}?{urlencode(params)}"
    return RedirectResponse(path, status_code=302)


@router.get("/jobs", response_class=HTMLResponse)
def jobs_page(request: Request, _: str = Depends(require_login_redirect)):
    conn = connect_db(request.app.state.db_path)
    try:
        jobs = list_jobs(conn)
    finally:
        conn.close()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "jobs.html",
        {
            "request": request,
            "jobs": jobs,
            "show_nav": True,
            "notice": request.query_params.get("notice"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail(request: Request, job_id: int, _: str = Depends(require_login_redirect)):
    conn = connect_db(request.app.state.db_path)
    try:
        job = get_job(conn, job_id)
        library = get_library(conn, int(job["library_id"])) if job is not None else None
        meili_health = _get_meili_health_for_request(conn, request) if job is not None else None
        active_profile = get_active_profile(conn, int(job["library_id"])) if job is not None else None
        latest_job = get_latest_relevant_build_job(conn, int(job["library_id"])) if job is not None else None
        if job is not None:
            # Persist canonical-profile creation/normalization before readiness/search-link decisions use it.
            conn.commit()
    finally:
        conn.close()

    if job is None:
        raise HTTPException(status_code=404)

    library_status = None
    if library is not None and meili_health is not None and active_profile is not None:
        library_status = derive_library_status(
            meili_state=meili_health.state,
            has_dataset=job.get("dataset_id") is not None,
            config_valid=_active_profile_is_valid(active_profile),
            latest_relevant_job_status=latest_job["status"] if latest_job else None,
        )

    log_text = None
    if job.get("log_path"):
        data_dir = resolve_data_dir(
            getattr(request.app.state, "data_dir", None),
            request.app.state.db_path,
        )
        base_dir = resolve_jobs_dir(data_dir)
        log_path = Path(job["log_path"])
        if log_path.is_absolute():
            log_path = log_path.resolve()
        else:
            log_path = (data_dir / log_path).resolve()
        if log_path != base_dir and base_dir not in log_path.parents:
            raise HTTPException(status_code=404)
        if log_path.exists() and not log_path.is_file():
            raise HTTPException(status_code=404)
        if log_path.exists():
            max_bytes = 200 * 1024
            with open(log_path, "rb") as handle:
                log_text = handle.read(max_bytes).decode("utf-8", errors="replace")

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "job_detail.html",
        {
            "request": request,
            "job": job,
            "library": library,
            "library_status": library_status,
            "log_text": log_text,
            "show_nav": True,
        },
    )


@router.post("/jobs/run")
def run_next_job(
    request: Request,
    _: str = Depends(require_login_redirect),
    return_to: str = Form(""),
    csrf_token: str = Form(""),
):
    require_csrf(request, csrf_token)
    runner = JobRunner(
        db_path=request.app.state.db_path,
        data_dir=getattr(request.app.state, "data_dir", None),
    )
    target = return_to.strip() or "/jobs"

    claimed_job = runner.claim_next()
    if claimed_job is None:
        runner.shutdown()
        conn = connect_db(request.app.state.db_path)
        try:
            queue_blocked = has_queued_build_jobs(conn)
        finally:
            conn.close()
        if queue_blocked:
            return _redirect_with_message(
                target,
                error="Build did not start. Queued work is waiting for the running build to finish.",
            )
        return _redirect_with_message(target, error="Build did not start. No queued jobs were available.")

    def _run():
        try:
            runner.run_claimed(claimed_job)
        finally:
            runner.shutdown()

    thread = Thread(target=_run, daemon=True)
    try:
        thread.start()
    except Exception as exc:
        try:
            runner.fail_claimed(claimed_job, str(exc))
        finally:
            runner.shutdown()
        return _redirect_with_message(target, error="Build did not start. The worker could not start.")
    return _redirect_with_message(target, notice="Build started")
