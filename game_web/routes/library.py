import sqlite3

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from game_web.auth_guard import require_login
from game_web.services.library_service import list_libraries

router = APIRouter()


@router.get("/libraries", response_class=HTMLResponse)
def library_list(request: Request, _: str = Depends(require_login)):
    conn = sqlite3.connect(request.app.state.db_path)
    try:
        libraries = list_libraries(conn)
    finally:
        conn.close()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "library_list.html",
        {"request": request, "libraries": libraries},
    )
