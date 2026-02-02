from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from game_web.csrf import generate_csrf_token, get_or_create_csrf_token, require_csrf
from game_web.db import connect_db
from game_web.services.admin_user_service import create_admin, has_admin, verify_admin
from game_web.session import create_session, delete_session

router = APIRouter()


@router.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request):
    conn = connect_db(request.app.state.db_path)
    try:
        if has_admin(conn):
            return RedirectResponse("/login", status_code=302)
    finally:
        conn.close()
    csrf_token, should_set_cookie = get_or_create_csrf_token(request)
    templates = request.app.state.templates
    response = templates.TemplateResponse(
        request,
        "setup.html",
        {"request": request, "show_nav": False, "csrf_token": csrf_token},
    )
    if should_set_cookie:
        response.set_cookie(
            "csrf_token",
            csrf_token,
            httponly=False,
            samesite="lax",
            max_age=24 * 60 * 60,
            secure=request.url.scheme == "https",
        )
    return response


@router.post("/setup")
def setup_submit(
    request: Request, password: str = Form(""), csrf_token: str = Form("")
):
    require_csrf(request, csrf_token)
    password = password.strip()
    if not password or len(password) < 8:
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request,
            "setup.html",
            {
                "request": request,
                "error": "Password must be at least 8 characters",
                "show_nav": False,
                "csrf_token": csrf_token,
            },
            status_code=400,
        )
    conn = connect_db(request.app.state.db_path)
    try:
        if not has_admin(conn):
            user_id = create_admin(conn, password)
            if user_id is None:
                return RedirectResponse("/login", status_code=302)
    finally:
        conn.close()
    return RedirectResponse("/login", status_code=302)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    conn = connect_db(request.app.state.db_path)
    try:
        if not has_admin(conn):
            return RedirectResponse("/setup", status_code=302)
    finally:
        conn.close()
    csrf_token, should_set_cookie = get_or_create_csrf_token(request)
    templates = request.app.state.templates
    response = templates.TemplateResponse(
        request,
        "login.html",
        {"request": request, "show_nav": False, "csrf_token": csrf_token},
    )
    if should_set_cookie:
        response.set_cookie(
            "csrf_token",
            csrf_token,
            httponly=False,
            samesite="lax",
            max_age=24 * 60 * 60,
            secure=request.url.scheme == "https",
        )
    return response


@router.post("/login")
def login_submit(
    request: Request, password: str = Form(""), csrf_token: str = Form("")
):
    require_csrf(request, csrf_token)
    password = password.strip()
    if not password:
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "request": request,
                "error": "Password is required",
                "show_nav": False,
                "csrf_token": csrf_token,
            },
            status_code=400,
        )
    conn = connect_db(request.app.state.db_path)
    try:
        user_id = verify_admin(conn, password)
        if not user_id:
            templates = request.app.state.templates
            return templates.TemplateResponse(
                request,
                "login.html",
                {
                    "request": request,
                    "error": "Invalid password",
                    "show_nav": False,
                    "csrf_token": csrf_token,
                },
                status_code=400,
            )
        try:
            session_id = create_session(conn, user_id=user_id)
        except Exception:
            templates = request.app.state.templates
            return templates.TemplateResponse(
                request,
                "login.html",
                {
                    "request": request,
                    "error": "Session creation failed",
                    "show_nav": False,
                    "csrf_token": csrf_token,
                },
                status_code=500,
            )
    finally:
        conn.close()
    resp = RedirectResponse("/libraries", status_code=302)
    resp.set_cookie(
        "session",
        session_id,
        httponly=True,
        samesite="lax",
        max_age=24 * 60 * 60,
        secure=request.url.scheme == "https",
    )
    resp.set_cookie(
        "csrf_token",
        generate_csrf_token(),
        httponly=False,
        samesite="lax",
        max_age=24 * 60 * 60,
        secure=request.url.scheme == "https",
    )
    return resp


@router.post("/logout")
def logout(request: Request, csrf_token: str = Form("")):
    require_csrf(request, csrf_token)
    session_id = request.cookies.get("session")
    if session_id:
        conn = connect_db(request.app.state.db_path)
        try:
            delete_session(conn, session_id)
        finally:
            conn.close()
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("session")
    resp.delete_cookie("csrf_token")
    return resp
