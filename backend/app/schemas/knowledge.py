from datetime import date

from pydantic import BaseModel, ConfigDict


class DocumentUploadResponse(BaseModel):
    document_id: str
    source_name: str
    chunks_indexed: int
    events_extracted: int
    impacts_created: int = 0


class SearchHit(BaseModel):
    document_id: str
    chunk_id: str
    score: float
    source_name: str
    snippet: str


class SearchResponse(BaseModel):
    query: str
    total: int
    hits: list[SearchHit]


class ExternalEventOut(BaseModel):
    id: str
    event_type: str
    delta_value: float | None
    delta_unit: str | None
    effective_date: date | None
    confidence: float
    evidence: str
    document_id: str | None

    model_config = ConfigDict(from_attributes=True)
