from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from game_web.auth_guard import require_login_redirect
from game_web.db import connect_db
from game_web.services.embedding_profile import list_profiles
from game_web.services.library_service import list_libraries
from game_web.services.search_executor import execute_search

router = APIRouter()


@router.get("/search", response_class=HTMLResponse)
def search_page(
    request: Request,
    _: str = Depends(require_login_redirect),
    library: str | None = None,
    embedder: str | None = None,
    q: str | None = None,
):
    query_text = (q or "").strip()
    embedder = (embedder or "").strip() or None
    library_id = None
    if library:
        try:
            library_id = int(library)
        except ValueError:
            library_id = None
    conn = connect_db(request.app.state.db_path)
    try:
        libraries = list_libraries(conn)
        embedders = list_profiles(conn, library_id) if library_id is not None else []
    finally:
        conn.close()

    results = []
    error_message = None
    searched = bool(library_id is not None and embedder and query_text)
    if searched and library_id is not None and embedder is not None:
        try:
            results = execute_search(
                request.app.state.db_path,
                library_id,
                embedder,
                query_text,
            )
        except Exception:
            error_message = "Search failed"

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "search.html",
        {
            "request": request,
            "libraries": libraries,
            "embedders": embedders,
            "results": results,
            "searched": searched,
            "error_message": error_message,
            "selected_library": library_id,
            "selected_embedder": embedder,
            "query": query_text,
            "show_nav": True,
        },
    )
