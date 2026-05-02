from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from game_web.auth_guard import require_login_redirect
from game_web.csrf import require_csrf
from game_web.db import connect_db
from game_web.runtime import resolve_data_dir
from game_web.secrets import decrypt_secret, encrypt_secret, load_key
from game_web.services.meili_health_service import get_meili_health
from game_web.services.settings_service import clear_setting, get_setting, set_setting

router = APIRouter()


def _api_key_status(data_dir: Path, api_key_value: str | None) -> str:
    if api_key_value is None:
        return "Not set"
    if load_key(data_dir) is None:
        return "Reset required"
    decrypted = decrypt_secret(data_dir, api_key_value)
    return "Set" if decrypted else "Invalid"


def _settings_context(request: Request, meili_url: str, api_key_value: str | None) -> dict:
    data_dir = resolve_data_dir(
        getattr(request.app.state, "data_dir", None),
        request.app.state.db_path,
    )
    api_key_status = _api_key_status(data_dir, api_key_value)
    meili_api_key = decrypt_secret(data_dir, api_key_value) if api_key_value else None
    meili_health = get_meili_health(meili_url, meili_api_key)
    return {
        "request": request,
        "meili_url": meili_url,
        "api_key_status": api_key_status,
        "meili_status": meili_health.state.replace("_", " "),
        "meili_status_message": meili_health.message,
        "show_nav": True,
    }


def _redirect_with_notice(path: str, notice: str) -> RedirectResponse:
    return RedirectResponse(f"{path}?{urlencode({'notice': notice})}", status_code=302)


def _render_settings_result(
    request: Request,
    *,
    meili_url: str,
    api_key_value: str | None,
    error: str,
    status_code: int,
):
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            **_settings_context(request, meili_url, api_key_value),
            "error": error,
        },
        status_code=status_code,
    )


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, _: str = Depends(require_login_redirect)):
    conn = connect_db(request.app.state.db_path)
    try:
        meili_url = get_setting(conn, "meili_url") or ""
        api_key_value = get_setting(conn, "meili_api_key")
    finally:
        conn.close()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            **_settings_context(request, meili_url, api_key_value),
            "notice": request.query_params.get("notice"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/settings")
def settings_submit(
    request: Request,
    _: str = Depends(require_login_redirect),
    meili_url: str = Form(""),
    meili_api_key: str = Form(""),
    csrf_token: str = Form(""),
):
    require_csrf(request, csrf_token)
    meili_url = meili_url.strip()
    meili_api_key = meili_api_key.strip()
    data_dir = resolve_data_dir(getattr(request.app.state, "data_dir", None), request.app.state.db_path)

    conn = connect_db(request.app.state.db_path)
    try:
        existing_meili_url = get_setting(conn, "meili_url") or ""
        existing_api_key_value = get_setting(conn, "meili_api_key")
        try:
            set_setting(conn, "meili_url", meili_url, commit=False)
            try:
                if meili_api_key:
                    encrypted = encrypt_secret(data_dir, meili_api_key)
                    set_setting(conn, "meili_api_key", encrypted, commit=False)
                else:
                    clear_setting(conn, "meili_api_key", commit=False)
            except OSError:
                conn.rollback()
                return _render_settings_result(
                    request,
                    meili_url=meili_url,
                    api_key_value=existing_api_key_value,
                    error="Save failed. Failed to save API key",
                    status_code=400,
                )
        except Exception:
            conn.rollback()
            return _render_settings_result(
                request,
                meili_url=meili_url or existing_meili_url,
                api_key_value=existing_api_key_value,
                error="Save failed",
                status_code=500,
            )
        try:
            conn.commit()
        except Exception:
            conn.rollback()
            return _render_settings_result(
                request,
                meili_url=meili_url or existing_meili_url,
                api_key_value=existing_api_key_value,
                error="Save failed",
                status_code=500,
            )
    finally:
        conn.close()

    effective_api_key = meili_api_key or None

    meili_health = get_meili_health(meili_url, effective_api_key)
    if meili_health.state == "reachable":
        return _redirect_with_notice("/settings", "Saved and connected")
    return _redirect_with_notice("/settings", "Saved, but connection failed")
