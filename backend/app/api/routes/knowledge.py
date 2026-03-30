import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field, HttpUrl

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.context import SignalImpactOut
from app.schemas.knowledge import DocumentUploadResponse, ExternalEventOut, SearchResponse
from app.services.context import resolve_seller_id
from app.services.knowledge import ingest_document, ingest_document_from_url, list_external_events, search_documents
from app.services.signal_engine import list_signal_impacts

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class SourceURLRequest(BaseModel):
    url: HttpUrl


class ExternalSignalIn(BaseModel):
    source_system: str = Field(default="external_feed", min_length=2)
    title: str = Field(..., min_length=3)
    body: str = Field(..., min_length=10)
    source_url: HttpUrl | None = None
    published_at: datetime | None = None
    tags: list[str] | None = None


@router.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    source_url: str | None = None,
    db: Session = Depends(get_db),
) -> DocumentUploadResponse:
    content = await file.read()
    try:
        return ingest_document(
            db=db,
            filename=file.filename or "document.txt",
            content=content,
            source_url=source_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to index document: {exc}") from exc


@router.post("/documents/from-url", response_model=DocumentUploadResponse)
def upload_document_from_url(
    request: SourceURLRequest,
    db: Session = Depends(get_db),
) -> DocumentUploadResponse:
    try:
        return ingest_document_from_url(db=db, url=str(request.url))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch/index URL: {exc}") from exc


@router.post("/signals/ingest", response_model=DocumentUploadResponse)
def ingest_external_signal(
    request: ExternalSignalIn,
    db: Session = Depends(get_db),
) -> DocumentUploadResponse:
    published = request.published_at or datetime.now(timezone.utc)
    safe_source = re.sub(r"[^a-z0-9_-]+", "_", request.source_system.strip().lower())
    filename = f"{safe_source}_{published.strftime('%Y%m%d_%H%M%S')}.txt"
    lines = [
        f"Source system: {request.source_system}",
        f"Published at: {published.isoformat()}",
        f"Title: {request.title}",
    ]
    if request.tags:
        lines.append(f"Tags: {', '.join(request.tags)}")
    lines.extend(["", request.body.strip()])
    content = "\n".join(lines).encode("utf-8")

    try:
        return ingest_document(
            db=db,
            filename=filename,
            content=content,
            source_url=str(request.source_url) if request.source_url else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to ingest external signal: {exc}") from exc


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=2),
    top_k: int = Query(default=5, ge=1, le=20),
) -> SearchResponse:
    try:
        return search_documents(query=q, top_k=top_k)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Search failed: {exc}") from exc


@router.get("/events", response_model=list[ExternalEventOut])
def events(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[ExternalEventOut]:
    return list_external_events(db=db, limit=limit)


@router.get("/impacts", response_model=list[SignalImpactOut])
def impacts(
    seller_code: str = Query(default="default"),
    limit: int = Query(default=100, ge=1, le=500),
    relevant_only: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> list[SignalImpactOut]:
    seller_id = resolve_seller_id(db, seller_code)
    return list_signal_impacts(
        db=db,
        seller_id=seller_id,
        limit=limit,
        relevant_only=relevant_only,
    )
