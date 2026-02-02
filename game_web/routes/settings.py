from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from game_web.auth_guard import require_login_redirect
from game_web.csrf import require_csrf
from game_web.db import connect_db
from game_web.runtime import resolve_data_dir
from game_web.secrets import decrypt_secret, encrypt_secret, load_key
from game_web.services.settings_service import clear_setting, get_setting, set_setting

router = APIRouter()


def _api_key_status(data_dir: Path, api_key_value: str | None) -> str:
    if api_key_value is None:
        return "Not set"
    if load_key(data_dir) is None:
        return "Reset required"
    decrypted = decrypt_secret(data_dir, api_key_value)
    return "Set" if decrypted else "Invalid"


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, _: str = Depends(require_login_redirect)):
    conn = connect_db(request.app.state.db_path)
    try:
        meili_url = get_setting(conn, "meili_url") or ""
        api_key_value = get_setting(conn, "meili_api_key")
    finally:
        conn.close()

    data_dir = resolve_data_dir(getattr(request.app.state, "data_dir", None), request.app.state.db_path)
    api_key_status = _api_key_status(data_dir, api_key_value)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "request": request,
            "meili_url": meili_url,
            "api_key_status": api_key_status,
            "show_nav": True,
        },
    )


@router.post("/settings")
def settings_submit(
    request: Request,
    _: str = Depends(require_login_redirect),
    meili_url: str = Form(""),
    meili_api_key: str = Form(""),
    clear_api_key: str = Form(""),
    csrf_token: str = Form(""),
):
    require_csrf(request, csrf_token)
    meili_url = meili_url.strip()
    meili_api_key = meili_api_key.strip()
    clear_requested = bool(clear_api_key.strip())
    data_dir = resolve_data_dir(getattr(request.app.state, "data_dir", None), request.app.state.db_path)

    conn = connect_db(request.app.state.db_path)
    try:
        set_setting(conn, "meili_url", meili_url, commit=False)
        if meili_api_key:
            try:
                encrypted = encrypt_secret(data_dir, meili_api_key)
            except OSError:
                conn.rollback()
                api_key_value = get_setting(conn, "meili_api_key")
                api_key_status = _api_key_status(data_dir, api_key_value)
                templates = request.app.state.templates
                return templates.TemplateResponse(
                    request,
                    "settings.html",
                    {
                        "request": request,
                        "meili_url": meili_url,
                        "api_key_status": api_key_status,
                        "error": "Failed to save API key",
                        "show_nav": True,
                    },
                    status_code=400,
                )
            set_setting(conn, "meili_api_key", encrypted, commit=False)
        elif clear_requested:
            clear_setting(conn, "meili_api_key", commit=False)
        conn.commit()
    finally:
        conn.close()

    return RedirectResponse("/settings", status_code=302)
