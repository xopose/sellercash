from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def healthcheck() -> dict[str, str | bool]:
    settings = get_settings()
    return {"status": "ok", "auth_enabled": settings.auth_enabled}
