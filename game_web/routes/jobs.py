from pathlib import Path
from threading import Thread

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from game_web.auth_guard import require_login_redirect
from game_web.csrf import require_csrf
from game_web.db import connect_db
from game_web.runtime import resolve_data_dir, resolve_jobs_dir
from game_web.services.job_runner import JobRunner
from game_web.services.job_service import get_job, list_jobs

router = APIRouter()


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
        {"request": request, "jobs": jobs, "show_nav": True},
    )


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail(request: Request, job_id: int, _: str = Depends(require_login_redirect)):
    conn = connect_db(request.app.state.db_path)
    try:
        job = get_job(conn, job_id)
    finally:
        conn.close()

    if job is None:
        raise HTTPException(status_code=404)

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
        {"request": request, "job": job, "log_text": log_text, "show_nav": True},
    )


@router.post("/jobs/run")
def run_next_job(
    request: Request,
    _: str = Depends(require_login_redirect),
    csrf_token: str = Form(""),
):
    require_csrf(request, csrf_token)
    runner = JobRunner(
        db_path=request.app.state.db_path,
        data_dir=getattr(request.app.state, "data_dir", None),
    )

    def _run():
        try:
            runner.run_next()
        finally:
            runner.shutdown()

    thread = Thread(target=_run, daemon=True)
    thread.start()
    return Response(status_code=202)
