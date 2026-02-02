import sqlite3

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from game_web.auth_guard import require_login_redirect
from game_web.csrf import require_csrf
from game_web.db import connect_db
from game_web.services.library_service import create_library, delete_library, list_libraries

router = APIRouter()


@router.get("/libraries", response_class=HTMLResponse)
def library_list(request: Request, _: str = Depends(require_login_redirect)):
    conn = connect_db(request.app.state.db_path)
    try:
        libraries = list_libraries(conn)
    finally:
        conn.close()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "library_list.html",
        {"request": request, "libraries": libraries, "show_nav": True},
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
            libraries = list_libraries(conn)
        finally:
            conn.close()
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request,
            "library_list.html",
            {
                "request": request,
                "libraries": libraries,
                "error": error,
                "show_nav": True,
            },
            status_code=400,
        )

    conn = connect_db(request.app.state.db_path)
    try:
        create_library(conn, name=name, index_uid=index_uid, description=description_value)
    except sqlite3.IntegrityError:
        conn.rollback()
        libraries = list_libraries(conn)
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request,
            "library_list.html",
            {
                "request": request,
                "libraries": libraries,
                "error": "Name or Index UID already exists",
                "show_nav": True,
            },
            status_code=400,
        )
    finally:
        conn.close()

    return RedirectResponse("/libraries", status_code=302)


@router.post("/libraries/{library_id}/delete")
def library_delete(
    request: Request,
    library_id: int,
    _: str = Depends(require_login_redirect),
    csrf_token: str = Form(""),
):
    require_csrf(request, csrf_token)
    conn = connect_db(request.app.state.db_path)
    try:
        deleted = delete_library(conn, library_id)
    finally:
        conn.close()

    if not deleted:
        raise HTTPException(status_code=404)

    return RedirectResponse("/libraries", status_code=302)
