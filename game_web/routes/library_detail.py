import datetime
import sqlite3

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from game_web.auth_guard import require_login_redirect
from game_web.csrf import require_csrf
from game_web.db import connect_db
from game_web.runtime import resolve_data_dir
from game_web.services.dataset_service import UploadTooLarge, save_upload
from game_web.services.embedding_profile import add_profile, list_profiles
from game_web.services import job_service
from game_web.services.library_service import get_library

router = APIRouter()


@router.get("/libraries/{library_id}", response_class=HTMLResponse)
def library_detail(
    request: Request,
    library_id: int,
    _: str = Depends(require_login_redirect),
):
    conn = connect_db(request.app.state.db_path)
    try:
        library = get_library(conn, library_id)
        profiles = list_profiles(conn, library_id=library_id)
    finally:
        conn.close()

    if library is None:
        raise HTTPException(status_code=404)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "library_detail.html",
        {
            "request": request,
            "library": library,
            "profiles": profiles,
            "show_nav": True,
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
            library = get_library(conn, library_id)
            profiles = list_profiles(conn, library_id=library_id)
        finally:
            conn.close()
        if library is None:
            raise HTTPException(status_code=404)
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request,
            "library_detail.html",
            {
                "request": request,
                "library": library,
                "profiles": profiles,
                "error": message,
                "show_nav": True,
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
        conn.commit()
    except UploadTooLarge:
        conn.rollback()
        raise HTTPException(status_code=413)
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

    return RedirectResponse("/jobs", status_code=302)


@router.post("/libraries/{library_id}/profiles/create")
def profile_create(
    request: Request,
    library_id: int,
    _: str = Depends(require_login_redirect),
    key: str = Form(""),
    model_name: str = Form(""),
    use_fp16: str = Form("0"),
    max_length: str = Form("128"),
    variant: str = Form("raw"),
    enabled: str = Form("1"),
    csrf_token: str = Form(""),
):
    require_csrf(request, csrf_token)
    key_value = key.strip()
    model_value = model_name.strip()
    variant_value = variant.strip() or "raw"

    def render_error(message: str, status_code: int = 400):
        conn = connect_db(request.app.state.db_path)
        try:
            library = get_library(conn, library_id)
            profiles = list_profiles(conn, library_id=library_id)
        finally:
            conn.close()
        if library is None:
            raise HTTPException(status_code=404)
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request,
            "library_detail.html",
            {
                "request": request,
                "library": library,
                "profiles": profiles,
                "error": message,
                "show_nav": True,
            },
            status_code=status_code,
        )

    if not key_value or not model_value:
        return render_error("Key and model name are required")

    try:
        use_fp16_value = int(use_fp16)
    except ValueError:
        return render_error("Use FP16 must be 0 or 1")
    if use_fp16_value not in (0, 1):
        return render_error("Use FP16 must be 0 or 1")

    try:
        enabled_value = int(enabled)
    except ValueError:
        return render_error("Enabled must be 0 or 1")
    if enabled_value not in (0, 1):
        return render_error("Enabled must be 0 or 1")

    try:
        max_length_value = int(max_length)
    except ValueError:
        return render_error("Max length must be greater than 0")
    if max_length_value <= 0:
        return render_error("Max length must be greater than 0")

    conn = connect_db(request.app.state.db_path)
    try:
        library = get_library(conn, library_id)
        if library is None:
            raise HTTPException(status_code=404)
        try:
            add_profile(
                conn,
                library_id=library_id,
                key=key_value,
                model_name=model_value,
                use_fp16=use_fp16_value,
                max_length=max_length_value,
                variant=variant_value,
                enabled=enabled_value,
            )
        except sqlite3.IntegrityError:
            conn.rollback()
            return render_error("Profile key already exists")
    finally:
        conn.close()

    return RedirectResponse(f"/libraries/{library_id}", status_code=302)
