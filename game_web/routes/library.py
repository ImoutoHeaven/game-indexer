import sqlite3
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from game_web.auth_guard import require_login_redirect
from game_web.csrf import require_csrf
from game_web.db import connect_db
from game_web.runtime import resolve_data_dir
from game_web.secrets import decrypt_secret
from game_web.services.embedding_profile import get_active_profile
from game_web.services.job_service import get_latest_dataset_for_library, get_latest_relevant_build_job
from game_web.services.library_service import create_library, delete_library, list_libraries
from game_web.services.library_status import derive_library_status
from game_web.services.meili_health_service import get_meili_health
from game_web.services.settings_service import get_setting

router = APIRouter()


def _active_profile_is_valid(profile: dict) -> bool:
    model_name = str(profile.get("model_name", "")).strip()
    if not model_name:
        return False
    try:
        use_fp16 = int(profile.get("use_fp16", 0))
        max_length = int(profile.get("max_length", 0))
    except (TypeError, ValueError):
        return False
    return use_fp16 in (0, 1) and max_length > 0


def _get_meili_health_for_request(conn, request: Request):
    data_dir = resolve_data_dir(
        getattr(request.app.state, "data_dir", None),
        request.app.state.db_path,
    )
    meili_url = (get_setting(conn, "meili_url") or "").strip()
    api_key_value = get_setting(conn, "meili_api_key")
    meili_api_key = decrypt_secret(data_dir, api_key_value) if api_key_value else None
    return get_meili_health(meili_url, meili_api_key)


def _row_action_for_status(library_id: int, readiness_state: str) -> dict[str, str]:
    """Map one readiness state to the frozen libraries-row CTA contract."""
    if readiness_state == "Needs setup":
        return {"href": "/settings", "label": "Open settings"}
    if readiness_state in {"Needs dataset", "Failed"}:
        return {"href": f"/libraries/{library_id}", "label": "Open library"}
    if readiness_state in {"Queued", "Building"}:
        return {"href": "/jobs", "label": "View jobs"}
    return {"href": f"/search?library={library_id}", "label": "Search"}


def _library_list_context(conn, request: Request) -> dict:
    meili_health = _get_meili_health_for_request(conn, request)
    libraries = []
    for library in list_libraries(conn):
        active_profile = get_active_profile(conn, library["id"])
        latest_dataset = get_latest_dataset_for_library(conn, library["id"])
        latest_job = get_latest_relevant_build_job(conn, library["id"])
        status = derive_library_status(
            meili_state=meili_health.state,
            has_dataset=latest_dataset is not None,
            config_valid=_active_profile_is_valid(active_profile),
            latest_relevant_job_status=latest_job["status"] if latest_job else None,
        )
        libraries.append(
            {
                **library,
                "status": status,
                "row_action": _row_action_for_status(library["id"], status.state),
                "latest_dataset_filename": latest_dataset["filename"] if latest_dataset else None,
                "latest_build_status": latest_job["status"] if latest_job else None,
            }
        )
    conn.commit()
    reminder = None
    if meili_health.state != "reachable":
        reminder = {
            "message": f"Meilisearch status: {meili_health.message}",
            "href": "/settings",
            "label": "Open settings",
        }
    return {
        "request": request,
        "libraries": libraries,
        "settings_reminder": reminder,
        "show_nav": True,
    }


def _redirect_with_message(path: str, *, notice: str | None = None, error: str | None = None) -> RedirectResponse:
    params = {}
    if notice:
        params["notice"] = notice
    if error:
        params["error"] = error
    if params:
        path = f"{path}?{urlencode(params)}"
    return RedirectResponse(path, status_code=302)


@router.get("/libraries", response_class=HTMLResponse)
def library_list(request: Request, _: str = Depends(require_login_redirect)):
    conn = connect_db(request.app.state.db_path)
    try:
        context = _library_list_context(conn, request)
    finally:
        conn.close()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "library_list.html",
        {
            **context,
            "notice": request.query_params.get("notice"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/libraries/create")
def library_create(
    request: Request,
    _: str = Depends(require_login_redirect),
    name: str = Form(""),
    index_uid: str = Form(""),
    description: str = Form(""),
    csrf_token: str = Form(""),
):
    require_csrf(request, csrf_token)
    name = name.strip()
    index_uid = index_uid.strip()
    description = description.strip()
    if description == "":
        description_value = None
    else:
        description_value = description

    error = None
    if not name:
        error = "Name is required"
    elif not index_uid:
        error = "Index UID is required"

    if error is not None:
        conn = connect_db(request.app.state.db_path)
        try:
            context = _library_list_context(conn, request)
        finally:
            conn.close()
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request,
            "library_list.html",
            {
                **context,
                "error": error,
            },
            status_code=400,
        )

    conn = connect_db(request.app.state.db_path)
    try:
        create_library(conn, name=name, index_uid=index_uid, description=description_value)
    except sqlite3.IntegrityError:
        conn.rollback()
        context = _library_list_context(conn, request)
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request,
            "library_list.html",
            {
                **context,
                "error": "Name or Index UID already exists",
            },
            status_code=400,
        )
    finally:
        conn.close()

    return _redirect_with_message("/libraries", notice="Library created")


@router.post("/libraries/{library_id}/delete")
def library_delete(
    request: Request,
    library_id: int,
    _: str = Depends(require_login_redirect),
    csrf_token: str = Form(""),
): 
    require_csrf(request, csrf_token)
    data_dir = resolve_data_dir(
        getattr(request.app.state, "data_dir", None),
        request.app.state.db_path,
    )
    conn = connect_db(request.app.state.db_path)
    try:
        deleted = delete_library(conn, library_id, data_dir=data_dir)
    except (OSError, sqlite3.DatabaseError):
        conn.rollback()
        return _redirect_with_message("/libraries", error="Library delete failed. The library was not removed.")
    finally:
        conn.close()

    if not deleted:
        raise HTTPException(status_code=404)

    return _redirect_with_message("/libraries", notice="Library deleted")
