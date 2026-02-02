import logging
from pathlib import Path

from fastapi import Body, FastAPI
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from game_web.db import connect_db, init_db
from game_web.routes.library import router as library_router
from game_web.routes.search import router as search_router
from game_web.session import create_session


def create_app(db_path: str = "app.db") -> FastAPI:
    init_db(db_path)
    app = FastAPI()
    app.state.db_path = db_path
    template_dir = Path(__file__).resolve().parent / "templates"
    app.state.templates = Jinja2Templates(directory=str(template_dir))
    app.include_router(library_router)
    app.include_router(search_router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/login")
    def login(payload: dict = Body(...)):
        username = payload.get("username")
        password = payload.get("password")
        if username != "admin" or password != "admin":
            return JSONResponse({"detail": "invalid credentials"}, status_code=401)
        conn = connect_db(app.state.db_path)
        try:
            session_id = create_session(conn, user_id=1)
        except Exception:
            logging.exception("session creation failed")
            return JSONResponse({"detail": "session creation failed"}, status_code=500)
        finally:
            conn.close()
        response = RedirectResponse("/libraries", status_code=302)
        response.set_cookie("session", session_id, httponly=True, samesite="Lax")
        return response

    return app
