from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from game_web.auth_guard import require_login_redirect
from game_web.db import connect_db
from game_web.routes.library import _active_profile_is_valid, _get_meili_health_for_request
from game_web.services.embedding_profile import get_active_profile
from game_web.services.job_service import get_latest_dataset_for_library, get_latest_relevant_build_job
from game_web.services.library_service import list_libraries
from game_web.services.library_status import derive_library_status
from game_web.services.search_executor import (
    SearchConnectionError,
    SearchExecutionError,
    SearchModelError,
    SearchNotReadyError,
    execute_search,
)

router = APIRouter()


def _searchable_libraries(conn, request: Request) -> list[dict]:
    meili_health = _get_meili_health_for_request(conn, request)
    searchable = []
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
        if status.state == "Searchable":
            searchable.append(library)
    conn.commit()
    return searchable


@router.get("/search", response_class=HTMLResponse)
def search_page(
    request: Request,
    _: str = Depends(require_login_redirect),
    library: str | None = None,
    q: str | None = None,
):
    query_text = (q or "").strip()
    library_id = None
    if library:
        try:
            library_id = int(library)
        except ValueError:
            library_id = None
    conn = connect_db(request.app.state.db_path)
    try:
        libraries = _searchable_libraries(conn, request)
    finally:
        conn.close()

    results = []
    error_message = None
    searched = bool(library_id is not None and query_text)
    if searched and library_id is not None:
        try:
            results = execute_search(
                request.app.state.db_path,
                library_id,
                query_text,
                data_dir=getattr(request.app.state, "data_dir", None),
            )
        except SearchNotReadyError as exc:
            error_message = str(exc)
        except SearchConnectionError as exc:
            error_message = str(exc)
        except SearchModelError as exc:
            error_message = str(exc)
        except SearchExecutionError as exc:
            error_message = str(exc)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "search.html",
        {
            "request": request,
            "libraries": libraries,
            "results": results,
            "searched": searched,
            "error_message": error_message,
            "selected_library": library_id,
            "query": query_text,
            "show_nav": True,
        },
    )
