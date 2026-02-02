from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/search", response_class=HTMLResponse)
def search_page(request: Request):
    templates = request.app.state.templates
    # Placeholder lists until database-backed options are wired.
    return templates.TemplateResponse(
        "search.html",
        {"request": request, "libraries": [], "embedders": []},
    )
