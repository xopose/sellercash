from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict


class FinanceEventIn(BaseModel):
    event_date: date
    event_type: str
    amount: float
    status: str = "fact"
    source: str | None = None
    currency: str = "RUB"
    payload: dict[str, Any] | None = None


class FinanceImportResult(BaseModel):
    imported_rows: int
    skipped_rows: int
    by_type: dict[str, int]


class FinanceEventOut(BaseModel):
    id: str
    event_date: date
    event_type: str
    amount: float
    status: str
    source: str | None
    currency: str

    model_config = ConfigDict(from_attributes=True)
