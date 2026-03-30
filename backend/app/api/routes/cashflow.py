from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.cashflow import ExplainResponse, ForecastRequest, ForecastResponse, ScenarioRequest, ScenarioResponse
from app.services.cashflow import explain_cashflow, run_forecast, run_scenario

router = APIRouter(prefix="/cashflow", tags=["cashflow"])


@router.post("/forecast", response_model=ForecastResponse)
def forecast(
    request: ForecastRequest,
    db: Session = Depends(get_db),
) -> ForecastResponse:
    return run_forecast(db, request)


@router.post("/scenario", response_model=ScenarioResponse)
def scenario(
    request: ScenarioRequest,
    db: Session = Depends(get_db),
) -> ScenarioResponse:
    return run_scenario(db, request)


@router.get("/explain", response_model=ExplainResponse)
def explain(
    seller_code: str = Query(default="default"),
    db: Session = Depends(get_db),
) -> ExplainResponse:
    return explain_cashflow(db, seller_code=seller_code)
