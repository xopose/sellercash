from fastapi import APIRouter, Depends

from app.api.routes.auth import router as auth_router
from app.api.routes.cashflow import router as cashflow_router
from app.api.routes.context import router as context_router
from app.api.routes.finance import router as finance_router
from app.api.routes.health import router as health_router
from app.api.routes.knowledge import router as knowledge_router
from app.core.auth import require_auth

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)

protected_router = APIRouter(dependencies=[Depends(require_auth)])
protected_router.include_router(finance_router)
protected_router.include_router(cashflow_router)
protected_router.include_router(knowledge_router)
protected_router.include_router(context_router)

api_router.include_router(protected_router)
