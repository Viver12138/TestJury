from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

router = APIRouter(include_in_schema=False)


@router.get("/")
async def console():
    return FileResponse(Path(__file__).resolve().parents[1] / "web/index.html", media_type="text/html",
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/ui-config")
async def configuration(request: Request):
    settings = request.app.state.settings
    return {"mode": settings.review_model_mode, "topology": settings.review_topology,
            "knowledge_enabled": settings.knowledge_enabled,
            "access_mode": "local" if settings.local_access_without_key else "api_key"}
