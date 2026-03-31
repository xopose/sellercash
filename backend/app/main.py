from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.db.session import Base, SessionLocal, engine
from app.services.context import ensure_default_seller_context
from app.services.knowledge import ensure_index

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "SellerCash API"
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_default_seller_context(db)
    finally:
        db.close()
    try:
        ensure_index()
    except Exception:
        # OpenSearch can be temporarily unavailable on cold start.
        pass


@app.get("/")
def home() -> FileResponse:
    static_file = Path(__file__).parent / "static" / "index.html"
    return FileResponse(static_file)
