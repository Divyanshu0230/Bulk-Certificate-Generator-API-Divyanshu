from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.database import database_ready

router = APIRouter(tags=["health"])


@router.get("/health", summary="Process health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/ready", summary="Database readiness")
def ready():
    if not database_ready():
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok"}
