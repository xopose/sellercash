from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class SellerContextItemCreate(BaseModel):
    seller_code: str = Field(default="default")
    seller_name: str = Field(default="Default Seller")
    sku: str = Field(..., min_length=2)
    category: str | None = None
    origin_country: str | None = None
    supplier_name: str | None = None
    route_name: str | None = None
    product_keywords: str | None = None
    is_active: bool = True


class SellerContextItemOut(BaseModel):
    id: str
    seller_id: str
    sku: str
    category: str | None
    origin_country: str | None
    supplier_name: str | None
    route_name: str | None
    product_keywords: str | None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class SignalImpactOut(BaseModel):
    id: str
    external_event_id: str
    seller_id: str
    context_item_id: str | None
    is_relevant: bool
    relevance_score: float
    impact_type: str
    impact_value: float | None
    effective_date: date
    details: dict | None
    evidence: str

    model_config = ConfigDict(from_attributes=True)
