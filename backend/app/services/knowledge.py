from __future__ import annotations

import re
from datetime import date
from io import BytesIO
from uuid import uuid4

import httpx
from minio import Minio
from opensearchpy import OpenSearch, helpers
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Document, DocumentChunk, ExternalEvent
from app.schemas.knowledge import DocumentUploadResponse, ExternalEventOut, SearchHit, SearchResponse
from app.services.signal_engine import apply_event_impacts

settings = get_settings()


def get_opensearch_client() -> OpenSearch:
    return OpenSearch(
        hosts=[settings.opensearch_url],
        http_compress=True,
        verify_certs=False,
    )


def get_minio_client() -> Minio:
    return Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def ensure_index() -> None:
    client = get_opensearch_client()
    if client.indices.exists(settings.opensearch_index):
        return

    body = {
        "settings": {
            "index": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
            }
        },
        "mappings": {
            "properties": {
                "document_id": {"type": "keyword"},
                "chunk_id": {"type": "keyword"},
                "source_name": {"type": "text"},
                "text": {"type": "text"},
                "uploaded_at": {"type": "date"},
            }
        },
    }
    client.indices.create(index=settings.opensearch_index, body=body)


def _extract_text(content: bytes, filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        reader = PdfReader(BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages).replace("\ufeff", "").strip()

    try:
        return content.decode("utf-8").replace("\ufeff", "").strip()
    except UnicodeDecodeError:
        return content.decode("latin-1", errors="ignore").replace("\ufeff", "").strip()


def _chunk_text(text: str, chunk_size: int = 900, overlap: int = 150) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        chunk = normalized[start:end]
        if end < len(normalized):
            split = chunk.rfind(" ")
            if split > chunk_size * 0.5:
                chunk = chunk[:split]
                end = start + split
        chunks.append(chunk.strip())
        if end >= len(normalized):
            break
        start = max(end - overlap, start + 1)

    return [c for c in chunks if c]


_RU_MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}

_EN_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _extract_date(fragment: str) -> date | None:
    match = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b", fragment)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year_raw = match.group(3)
        year = int(year_raw)
        if year < 100:
            year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            pass

    month_pattern = re.search(r"(\d{1,2})\s+([а-яa-z]+)(?:\s+(\d{4}))?", fragment.lower())
    if month_pattern:
        day = int(month_pattern.group(1))
        month_word = month_pattern.group(2)
        year = int(month_pattern.group(3)) if month_pattern.group(3) else date.today().year
        month = _RU_MONTHS.get(month_word) or _EN_MONTHS.get(month_word)
        if month:
            try:
                return date(year, month, day)
            except ValueError:
                pass

    return None


def _to_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _extract_events_from_chunk(chunk: str) -> list[dict]:
    events: list[dict] = []

    commission = re.finditer(
        r"(?:комисси\w*|commission)[^\n]{0,80}?([+-]?\d+[.,]?\d*)\s*%[^\n]{0,80}",
        chunk,
        flags=re.IGNORECASE,
    )
    for match in commission:
        start = max(0, match.start() - 60)
        end = min(len(chunk), match.end() + 80)
        fragment = chunk[start:end].strip()
        events.append(
            {
                "event_type": "commission_change_pct",
                "delta_value": _to_float(match.group(1)),
                "delta_unit": "pct",
                "effective_date": _extract_date(fragment),
                "confidence": 0.85,
                "evidence": fragment,
            }
        )

    logistics = re.finditer(
        r"(?:логистик\w*|shipping|delivery)[^\n]{0,80}?([+-]?\d+[.,]?\d*)\s*%[^\n]{0,80}",
        chunk,
        flags=re.IGNORECASE,
    )
    for match in logistics:
        start = max(0, match.start() - 60)
        end = min(len(chunk), match.end() + 80)
        fragment = chunk[start:end].strip()
        events.append(
            {
                "event_type": "logistics_change_pct",
                "delta_value": _to_float(match.group(1)),
                "delta_unit": "pct",
                "effective_date": _extract_date(fragment),
                "confidence": 0.8,
                "evidence": fragment,
            }
        )

    payouts = re.finditer(
        r"(?:срок\w* выплат|payout\s+delay|settlement\s+period)[^\n]{0,80}?([+-]?\d+)\s*(?:дн|дней|day)",
        chunk,
        flags=re.IGNORECASE,
    )
    for match in payouts:
        start = max(0, match.start() - 60)
        end = min(len(chunk), match.end() + 80)
        fragment = chunk[start:end].strip()
        events.append(
            {
                "event_type": "payout_delay_days",
                "delta_value": _to_float(match.group(1)),
                "delta_unit": "days",
                "effective_date": _extract_date(fragment),
                "confidence": 0.78,
                "evidence": fragment,
            }
        )

    supply = re.finditer(
        r"(?:задерж\w+[^\n]{0,120}(?:фур|грузов|поставк)|border[^\n]{0,120}delay|truck[^\n]{0,120}delay|detain\w+[^\n]{0,120}truck)",
        chunk,
        flags=re.IGNORECASE,
    )
    for match in supply:
        start = max(0, match.start() - 80)
        end = min(len(chunk), match.end() + 120)
        fragment = chunk[start:end].strip()
        delay_match = re.search(r"([+-]?\d+)\s*(?:дн|дней|day)", fragment, flags=re.IGNORECASE)
        delay_days = _to_float(delay_match.group(1)) if delay_match else None
        events.append(
            {
                "event_type": "supply_disruption",
                "delta_value": delay_days,
                "delta_unit": "days",
                "effective_date": _extract_date(fragment) or date.today(),
                "confidence": 0.72,
                "evidence": fragment,
            }
        )

    return events


def _store_raw_document(filename: str, content: bytes) -> str | None:
    client = get_minio_client()
    try:
        if not client.bucket_exists(settings.minio_bucket):
            client.make_bucket(settings.minio_bucket)
    except Exception:
        return None

    object_key = f"{uuid4()}_{filename}"
    stream = BytesIO(content)
    try:
        client.put_object(
            bucket_name=settings.minio_bucket,
            object_name=object_key,
            data=stream,
            length=len(content),
            content_type="application/octet-stream",
        )
        return object_key
    except Exception:
        return None


def ingest_document(*, db: Session, filename: str, content: bytes, source_url: str | None = None) -> DocumentUploadResponse:
    ensure_index()

    text = _extract_text(content, filename)
    if not text.strip():
        raise ValueError("Document has no readable text")

    chunks = _chunk_text(text)
    object_key = _store_raw_document(filename, content)

    doc = Document(source_name=filename, source_url=source_url, object_key=object_key, chunks_count=len(chunks))
    db.add(doc)
    db.flush()

    os_actions = []
    extracted_events_count = 0
    impacts_created = 0
    seen_events: set[tuple[str, float | None, str]] = set()
    event_rows: list[ExternalEvent] = []

    for idx, chunk in enumerate(chunks):
        chunk_id = str(uuid4())
        chunk_row = DocumentChunk(id=chunk_id, document_id=doc.id, chunk_no=idx, text=chunk)
        db.add(chunk_row)

        os_actions.append(
            {
                "_index": settings.opensearch_index,
                "_id": chunk_id,
                "_source": {
                    "document_id": doc.id,
                    "chunk_id": chunk_id,
                    "source_name": filename,
                    "text": chunk,
                    "uploaded_at": doc.uploaded_at.isoformat(),
                },
            }
        )

        for event in _extract_events_from_chunk(chunk):
            fingerprint = (event["event_type"], event["delta_value"], event["evidence"])
            if fingerprint in seen_events:
                continue
            seen_events.add(fingerprint)
            event_row = ExternalEvent(
                document_id=doc.id,
                event_type=event["event_type"],
                delta_value=event["delta_value"],
                delta_unit=event["delta_unit"],
                effective_date=event["effective_date"],
                confidence=event["confidence"],
                evidence=event["evidence"],
            )
            db.add(event_row)
            event_rows.append(event_row)
            extracted_events_count += 1

    db.flush()

    if os_actions:
        client = get_opensearch_client()
        helpers.bulk(client, os_actions)

    if event_rows:
        impacts_created = apply_event_impacts(db, event_rows)
    else:
        db.commit()

    return DocumentUploadResponse(
        document_id=doc.id,
        source_name=filename,
        chunks_indexed=len(chunks),
        events_extracted=extracted_events_count,
        impacts_created=impacts_created,
    )


def ingest_document_from_url(*, db: Session, url: str) -> DocumentUploadResponse:
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()

    file_name = url.rstrip("/").split("/")[-1] or "web_document.txt"
    content_type = response.headers.get("content-type", "")
    content = response.content

    if "text" in content_type and not file_name.lower().endswith((".txt", ".html", ".md")):
        file_name = f"{file_name}.txt"

    return ingest_document(db=db, filename=file_name, content=content, source_url=url)


def search_documents(*, query: str, top_k: int = 5) -> SearchResponse:
    ensure_index()
    client = get_opensearch_client()

    body = {
        "size": top_k,
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["text^2", "source_name"],
                "type": "best_fields",
            }
        },
        "highlight": {
            "fields": {
                "text": {},
            }
        },
    }

    result = client.search(index=settings.opensearch_index, body=body)
    hits: list[SearchHit] = []

    for item in result.get("hits", {}).get("hits", []):
        source = item.get("_source", {})
        highlights = item.get("highlight", {}).get("text", [])
        snippet = highlights[0] if highlights else source.get("text", "")[:240]
        hits.append(
            SearchHit(
                document_id=source.get("document_id", ""),
                chunk_id=source.get("chunk_id") or item.get("_id", ""),
                score=float(item.get("_score", 0.0)),
                source_name=source.get("source_name", "unknown"),
                snippet=snippet,
            )
        )

    total_raw = result.get("hits", {}).get("total", 0)
    total = total_raw.get("value", 0) if isinstance(total_raw, dict) else int(total_raw)

    return SearchResponse(query=query, total=total, hits=hits)


def list_external_events(db: Session, limit: int = 100) -> list[ExternalEventOut]:
    rows = (
        db.query(ExternalEvent)
        .order_by(ExternalEvent.effective_date.desc().nullslast(), ExternalEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    return [ExternalEventOut.model_validate(row) for row in rows]
