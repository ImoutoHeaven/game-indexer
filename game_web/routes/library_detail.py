import datetime
import sqlite3
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from game_web.auth_guard import require_login_redirect
from game_web.csrf import require_csrf
from game_web.db import connect_db
from game_web.routes.library import _active_profile_is_valid, _get_meili_health_for_request
from game_web.runtime import resolve_data_dir
from game_web.services.dataset_service import UploadTooLarge, save_upload
from game_web.services.embedding_profile import get_active_profile, upsert_active_profile
from game_web.services import job_service
from game_web.services.library_service import get_library
from game_web.services.library_status import derive_library_status

router = APIRouter()


def _redirect_with_notice(path: str, notice: str) -> RedirectResponse:
    return RedirectResponse(f"{path}?{urlencode({'notice': notice})}", status_code=302)


def _library_detail_context(conn, request: Request, library_id: int) -> dict | None:
    library = get_library(conn, library_id)
    if library is None:
        return None

    active_profile = get_active_profile(conn, library_id)
    latest_dataset = job_service.get_latest_dataset_for_library(conn, library_id)
    recent_build = job_service.get_latest_relevant_build_job(conn, library_id)
    meili_health = _get_meili_health_for_request(conn, request)
    library_status = derive_library_status(
        meili_state=meili_health.state,
        has_dataset=latest_dataset is not None,
        config_valid=_active_profile_is_valid(active_profile),
        latest_relevant_job_status=recent_build["status"] if recent_build else None,
    )
    conn.commit()
    return {
        "request": request,
        "library": library,
        "active_profile": active_profile,
        "library_status": library_status,
        "recent_build": recent_build,
        "show_nav": True,
    }


@router.get("/libraries/{library_id}", response_class=HTMLResponse)
def library_detail(
    request: Request,
    library_id: int,
    _: str = Depends(require_login_redirect),
):
    conn = connect_db(request.app.state.db_path)
    try:
        context = _library_detail_context(conn, request, library_id)
    finally:
        conn.close()

    if context is None:
        raise HTTPException(status_code=404)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "library_detail.html",
        {
            **context,
            "notice": request.query_params.get("notice"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/libraries/{library_id}/datasets/upload")
def dataset_upload(
    request: Request,
    library_id: int,
    _: str = Depends(require_login_redirect),
    file: UploadFile | None = File(None),
    csrf_token: str = Form(""),
): 
    require_csrf(request, csrf_token)

    def render_error(message: str, status_code: int = 400):
        conn = connect_db(request.app.state.db_path)
        try:
            context = _library_detail_context(conn, request, library_id)
        finally:
            conn.close()
        if context is None:
            raise HTTPException(status_code=404)
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request,
            "library_detail.html",
            {
                **context,
                "error": message,
            },
            status_code=status_code,
        )

    if file is None or not file.filename:
        return render_error("File is required")

    conn = connect_db(request.app.state.db_path)
    dataset = None
    data_dir = None
    try:
        library = get_library(conn, library_id)
        if library is None:
            raise HTTPException(status_code=404)
        data_dir = resolve_data_dir(
            getattr(request.app.state, "data_dir", None),
            request.app.state.db_path,
        )
        dataset = save_upload(
            conn,
            data_dir=data_dir,
            library_id=library_id,
            filename=file.filename,
            file_obj=file.file,
            commit=False,
        )
        dataset_id = dataset.get("id")
        if dataset_id is None:
            raise HTTPException(status_code=500)
        job_service.create_job(
            conn,
            library_id=library_id,
            dataset_id=int(dataset_id),
            job_type="build",
            status="queued",
            commit=False,
        )
        job_service.supersede_queued_jobs(conn, library_id)
    except UploadTooLarge:
        conn.rollback()
        return render_error("Upload too large", status_code=413)
    except Exception:
        conn.rollback()
        if dataset is not None:
            try:
                dataset_path = dataset.get("path")
                if dataset_path is not None and dataset_path.exists():
                    dataset_path.unlink()
            except OSError:
                pass
        raise
    finally:
        try:
            file.file.close()
        except OSError:
            pass
        conn.close()

    return _redirect_with_notice(f"/libraries/{library_id}", "Build job queued")


@router.post("/libraries/{library_id}/search-config")
def update_search_config(
    request: Request,
    library_id: int,
    _: str = Depends(require_login_redirect),
    model_name: str = Form(""),
    use_fp16: str = Form("0"),
    max_length: str = Form("128"),
    csrf_token: str = Form(""),
):
    require_csrf(request, csrf_token)

    def render_error(message: str, status_code: int = 400):
        conn = connect_db(request.app.state.db_path)
        try:
            context = _library_detail_context(conn, request, library_id)
        finally:
            conn.close()
        if context is None:
            raise HTTPException(status_code=404)
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request,
            "library_detail.html",
            {
                **context,
                "error": message,
            },
            status_code=status_code,
        )

    conn = connect_db(request.app.state.db_path)
    try:
        library = get_library(conn, library_id)
        if library is None:
            raise HTTPException(status_code=404)
        latest_dataset = job_service.get_latest_dataset_for_library(conn, library_id)
        try:
            changed = upsert_active_profile(
                conn,
                library_id=library_id,
                model_name=model_name,
                use_fp16=int(use_fp16),
                max_length=int(max_length),
                commit=False,
            )
        except ValueError as exc:
            conn.rollback()
            return render_error(str(exc))
        if changed and latest_dataset is not None:
            job_service.create_job(
                conn,
                library_id=library_id,
                dataset_id=int(latest_dataset["id"]),
                job_type="build",
                status="queued",
                commit=False,
            )
            job_service.supersede_queued_jobs(conn, library_id)
        else:
            conn.commit()
    finally:
        conn.close()

    return _redirect_with_notice(f"/libraries/{library_id}", "Search configuration saved")
