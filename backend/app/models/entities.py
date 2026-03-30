from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SellerProfile(Base):
    __tablename__ = "seller_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SellerContextItem(Base):
    __tablename__ = "seller_context_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    seller_id: Mapped[str] = mapped_column(String(36), ForeignKey("seller_profiles.id", ondelete="CASCADE"), index=True)
    sku: Mapped[str] = mapped_column(String(128), index=True)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    origin_country: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    supplier_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    route_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product_keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FinanceEvent(Base):
    __tablename__ = "finance_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    event_date: Mapped[date] = mapped_column(Date, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(16), default="fact", index=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_name: Mapped[str] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    chunks_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_no: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    indexed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ExternalEvent(Base):
    __tablename__ = "external_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    document_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    delta_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    delta_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    evidence: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ExternalSignalImpact(Base):
    __tablename__ = "external_signal_impacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    external_event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("external_events.id", ondelete="CASCADE"), index=True
    )
    seller_id: Mapped[str] = mapped_column(String(36), ForeignKey("seller_profiles.id", ondelete="CASCADE"), index=True)
    context_item_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("seller_context_items.id", ondelete="SET NULL"), nullable=True
    )
    is_relevant: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    impact_type: Mapped[str] = mapped_column(String(64), index=True)
    impact_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    effective_date: Mapped[date] = mapped_column(Date, index=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evidence: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
