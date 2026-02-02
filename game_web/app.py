from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from game_web.db import init_db
from game_web.routes.auth import router as auth_router
from game_web.routes.jobs import router as jobs_router
from game_web.routes.library import router as library_router
from game_web.routes.library_detail import router as library_detail_router
from game_web.routes.search import router as search_router
from game_web.routes.settings import router as settings_router
from game_web.runtime import resolve_data_dir


def create_app(db_path: str = "app.db", data_dir: str | Path | None = None) -> FastAPI:
    init_db(db_path)
    app = FastAPI()
    app.state.db_path = db_path
    app.state.data_dir = resolve_data_dir(data_dir, db_path)
    template_dir = Path(__file__).resolve().parent / "templates"
    app.state.templates = Jinja2Templates(directory=str(template_dir))
    app.include_router(auth_router)
    app.include_router(jobs_router)
    app.include_router(library_router)
    app.include_router(library_detail_router)
    app.include_router(search_router)
    app.include_router(settings_router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
