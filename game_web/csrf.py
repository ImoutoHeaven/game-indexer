import secrets

from fastapi import HTTPException, Request


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def get_or_create_csrf_token(request: Request) -> tuple[str, bool]:
    token = request.cookies.get("csrf_token")
    if token:
        return token, False
    return generate_csrf_token(), True


def require_csrf(request: Request, token: str) -> None:
    cookie_token = request.cookies.get("csrf_token")
    if not cookie_token or not token or cookie_token != token:
        raise HTTPException(status_code=403)
