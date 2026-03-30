from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class ForecastRequest(BaseModel):
    seller_code: str = Field(default="default")
    horizon_days: int = Field(default=60, ge=7, le=120)
    start_balance: float = Field(default=0.0)


class CashflowPoint(BaseModel):
    date: date
    inflow: float
    outflow: float
    net: float
    balance: float
    p10_balance: float
    p90_balance: float
    risk_negative: float


class ForecastAlert(BaseModel):
    level: str
    message: str
    alert_date: date | None = Field(default=None, serialization_alias="date", validation_alias="date")

    model_config = ConfigDict(populate_by_name=True)


class ForecastResponse(BaseModel):
    horizon_days: int
    start_balance: float
    ending_balance: float
    min_balance: float
    min_balance_date: date
    points: list[CashflowPoint]
    alerts: list[ForecastAlert]


class ScenarioRequest(BaseModel):
    seller_code: str = Field(default="default")
    horizon_days: int = Field(default=60, ge=7, le=120)
    start_balance: float = Field(default=0.0)
    ads_delta_pct: float = Field(default=0.0, ge=-1.0, le=1.0)
    price_delta_pct: float = Field(default=0.0, ge=-0.5, le=0.5)
    procurement_shift_days: int = Field(default=0, ge=-30, le=30)
    procurement_delta_pct: float = Field(default=0.0, ge=-1.0, le=1.0)


class ScenarioResponse(BaseModel):
    baseline_min_balance: float
    baseline_min_balance_date: date
    scenario_min_balance: float
    scenario_min_balance_date: date
    risk_reduction: float
    profit_delta_pct: float
    recommendation: str


class DriverOut(BaseModel):
    driver: str
    impact_estimate: float
    details: str
    source_document_id: str | None = None


class ExplainResponse(BaseModel):
    drivers: list[DriverOut]
