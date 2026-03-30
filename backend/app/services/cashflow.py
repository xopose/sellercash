from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ExternalEvent, ExternalSignalImpact, FinanceEvent
from app.schemas.cashflow import (
    CashflowPoint,
    DriverOut,
    ExplainResponse,
    ForecastAlert,
    ForecastRequest,
    ForecastResponse,
    ScenarioRequest,
    ScenarioResponse,
)
from app.services.context import resolve_seller_id

SALES_TYPES = {"sale", "sales", "order_paid", "продажа", "выручка"}
RETURN_TYPES = {"return", "refund", "возврат"}
ADS_TYPES = {"ads", "advertising", "реклама"}
LOGISTICS_TYPES = {"logistics", "shipping", "delivery", "логистика"}
STORAGE_TYPES = {"storage", "warehouse", "хранение"}
PENALTY_TYPES = {"penalty", "fine", "штраф"}
PROCUREMENT_TYPES = {"procurement", "purchase", "supplier_payment", "закупка"}


@dataclass
class SimulationAdjustments:
    ads_delta_pct: float = 0.0
    price_delta_pct: float = 0.0
    procurement_shift_days: int = 0
    procurement_delta_pct: float = 0.0


@dataclass
class BaselineStats:
    avg_daily_sales: float
    sales_trend_per_day: float
    sales_std: float
    return_rate: float
    avg_ads: float
    avg_logistics: float
    avg_storage: float
    avg_penalty: float
    avg_procurement: float


@dataclass
class PolicyParams:
    commission_rate: float = 0.13
    payout_delay_days: int = 14
    logistics_multiplier: float = 1.0
    sales_multiplier: float = 1.0
    procurement_shift_days: int = 0


@dataclass
class ExternalPolicyEvent:
    event_type: str
    delta_value: float | None
    effective_date: date | None
    evidence: str
    confidence: float
    document_id: str | None


@dataclass
class SimulationResult:
    points: list[CashflowPoint]
    min_balance: float
    min_balance_date: date
    ending_balance: float


def _daily_series(db: Session, types: set[str], lookback_days: int = 120) -> list[tuple[date, float]]:
    today = date.today()
    start = today - timedelta(days=lookback_days)

    rows = (
        db.execute(
            select(FinanceEvent.event_date, func.sum(FinanceEvent.amount))
            .where(FinanceEvent.status == "fact")
            .where(FinanceEvent.event_date >= start)
            .where(func.lower(FinanceEvent.event_type).in_(types))
            .group_by(FinanceEvent.event_date)
            .order_by(FinanceEvent.event_date)
        )
        .all()
    )

    return [(r[0], float(r[1])) for r in rows]


def _avg_abs_daily(db: Session, types: set[str], lookback_days: int = 120) -> float:
    rows = _daily_series(db, types, lookback_days)
    if not rows:
        return 0.0
    return sum(abs(v) for _, v in rows) / max(1, len(rows))


def _build_baseline(db: Session) -> BaselineStats:
    sales = _daily_series(db, SALES_TYPES)
    if not sales:
        return BaselineStats(
            avg_daily_sales=5000.0,
            sales_trend_per_day=15.0,
            sales_std=1200.0,
            return_rate=0.08,
            avg_ads=900.0,
            avg_logistics=700.0,
            avg_storage=220.0,
            avg_penalty=80.0,
            avg_procurement=1500.0,
        )

    values = [max(0.0, v) for _, v in sales]
    avg_sales = sum(values) / len(values)

    # Linear trend from first and last points keeps behavior deterministic for MVP.
    trend = 0.0
    if len(values) > 1:
        trend = (values[-1] - values[0]) / (len(values) - 1)

    mean = avg_sales
    variance = sum((v - mean) ** 2 for v in values) / max(1, len(values) - 1)
    std = math.sqrt(variance)

    returns = _avg_abs_daily(db, RETURN_TYPES)
    return_rate = min(0.35, max(0.01, returns / max(1.0, avg_sales)))

    return BaselineStats(
        avg_daily_sales=max(100.0, avg_sales),
        sales_trend_per_day=trend,
        sales_std=max(100.0, std),
        return_rate=return_rate,
        avg_ads=_avg_abs_daily(db, ADS_TYPES) or 900.0,
        avg_logistics=_avg_abs_daily(db, LOGISTICS_TYPES) or 700.0,
        avg_storage=_avg_abs_daily(db, STORAGE_TYPES) or 220.0,
        avg_penalty=_avg_abs_daily(db, PENALTY_TYPES) or 80.0,
        avg_procurement=_avg_abs_daily(db, PROCUREMENT_TYPES) or 1500.0,
    )


def _load_policy_events(db: Session, seller_id: str) -> list[ExternalPolicyEvent]:
    impact_rows = (
        db.execute(
            select(
                ExternalSignalImpact.impact_type,
                ExternalSignalImpact.impact_value,
                ExternalSignalImpact.effective_date,
                ExternalSignalImpact.evidence,
                ExternalEvent.document_id,
            )
            .join(ExternalEvent, ExternalEvent.id == ExternalSignalImpact.external_event_id, isouter=True)
            .where(ExternalSignalImpact.seller_id == seller_id)
            .where(ExternalSignalImpact.is_relevant.is_(True))
            .order_by(ExternalSignalImpact.effective_date.asc(), ExternalSignalImpact.created_at.asc())
        )
        .all()
    )

    if impact_rows:
        mapped_events: list[ExternalPolicyEvent] = []
        for row in impact_rows:
            mapped_type = {
                "commission_rate_delta_pct": "commission_change_pct",
                "logistics_cost_delta_pct": "logistics_change_pct",
                "payout_delay_delta_days": "payout_delay_days",
                "sales_drop_pct": "sales_drop_pct",
                "procurement_delay_days": "procurement_delay_days",
            }.get(row[0])
            if not mapped_type:
                continue
            mapped_events.append(
                ExternalPolicyEvent(
                    event_type=mapped_type,
                    delta_value=row[1],
                    effective_date=row[2],
                    evidence=row[3],
                    confidence=1.0,
                    document_id=row[4],
                )
            )
        return mapped_events

    rows = (
        db.execute(
            select(
                ExternalEvent.event_type,
                ExternalEvent.delta_value,
                ExternalEvent.effective_date,
                ExternalEvent.evidence,
                ExternalEvent.confidence,
                ExternalEvent.document_id,
            )
            .order_by(ExternalEvent.effective_date.asc().nullslast(), ExternalEvent.created_at.asc())
        )
        .all()
    )

    events: list[ExternalPolicyEvent] = []
    for row in rows:
        events.append(
            ExternalPolicyEvent(
                event_type=row[0],
                delta_value=row[1],
                effective_date=row[2],
                evidence=row[3],
                confidence=float(row[4]),
                document_id=row[5],
            )
        )
    return events


def _apply_policy_event(params: PolicyParams, event: ExternalPolicyEvent) -> None:
    if event.event_type == "commission_change_pct" and event.delta_value is not None:
        params.commission_rate = max(0.0, min(0.5, params.commission_rate + event.delta_value / 100.0))
    elif event.event_type == "logistics_change_pct" and event.delta_value is not None:
        params.logistics_multiplier = max(0.1, params.logistics_multiplier * (1 + event.delta_value / 100.0))
    elif event.event_type == "payout_delay_days" and event.delta_value is not None:
        params.payout_delay_days = max(1, min(45, int(params.payout_delay_days + event.delta_value)))
    elif event.event_type == "sales_drop_pct" and event.delta_value is not None:
        params.sales_multiplier = max(0.2, params.sales_multiplier * (1 + event.delta_value / 100.0))
    elif event.event_type == "procurement_delay_days" and event.delta_value is not None:
        params.procurement_shift_days = max(0, params.procurement_shift_days + int(event.delta_value))


def _policy_by_day(events: list[ExternalPolicyEvent], horizon_days: int) -> dict[date, PolicyParams]:
    today = date.today()
    params = PolicyParams()
    result: dict[date, PolicyParams] = {}

    events_by_date: dict[date, list[ExternalPolicyEvent]] = defaultdict(list)
    for event in events:
        if event.effective_date and event.effective_date <= today:
            _apply_policy_event(params, event)
        elif event.effective_date:
            events_by_date[event.effective_date].append(event)

    for offset in range(1, horizon_days + 1):
        day = today + timedelta(days=offset)
        for event in events_by_date.get(day, []):
            _apply_policy_event(params, event)

        result[day] = PolicyParams(
            commission_rate=params.commission_rate,
            payout_delay_days=params.payout_delay_days,
            logistics_multiplier=params.logistics_multiplier,
            sales_multiplier=params.sales_multiplier,
            procurement_shift_days=params.procurement_shift_days,
        )

    return result


def _procurement_spend(base: float, day_index: int, shift_days: int, delta_pct: float) -> float:
    spend = 0.0
    purchase_cycle = 14
    shifted_index = day_index - shift_days
    if shifted_index >= 0 and shifted_index % purchase_cycle == 0:
        spend = base * (1 + delta_pct)
    return max(0.0, spend)


def _sales_for_day(
    baseline: BaselineStats,
    day_index: int,
    adjustment: SimulationAdjustments,
    uncertainty_shift: float,
) -> float:
    base = baseline.avg_daily_sales + baseline.sales_trend_per_day * day_index
    weekly = 1 + 0.08 * math.sin((day_index % 7) * 2 * math.pi / 7)

    ads_factor = 1 + 0.35 * adjustment.ads_delta_pct
    unit_change = 1 - 1.2 * adjustment.price_delta_pct
    price_factor = 1 + adjustment.price_delta_pct

    value = base * weekly * ads_factor * unit_change * price_factor
    value += uncertainty_shift * baseline.sales_std
    return max(0.0, value)


def _simulate(
    baseline: BaselineStats,
    policy_by_day: dict[date, PolicyParams],
    horizon_days: int,
    start_balance: float,
    adjustment: SimulationAdjustments,
) -> SimulationResult:
    today = date.today()

    payout_queues = {
        "base": defaultdict(float),
        "low": defaultdict(float),
        "high": defaultdict(float),
    }
    returns_queues = {
        "base": defaultdict(float),
        "low": defaultdict(float),
        "high": defaultdict(float),
    }

    balance = start_balance
    p10_balance = start_balance
    p90_balance = start_balance

    points: list[CashflowPoint] = []
    min_balance = start_balance
    min_balance_date = today

    for day_idx in range(1, horizon_days + 1):
        day = today + timedelta(days=day_idx)
        policy = policy_by_day.get(day, PolicyParams())

        sales_base = _sales_for_day(baseline, day_idx, adjustment, uncertainty_shift=0.0) * policy.sales_multiplier
        sales_low = _sales_for_day(baseline, day_idx, adjustment, uncertainty_shift=-0.8) * policy.sales_multiplier
        sales_high = _sales_for_day(baseline, day_idx, adjustment, uncertainty_shift=0.8) * policy.sales_multiplier

        payout_day = day + timedelta(days=policy.payout_delay_days)
        payout_queues["base"][payout_day] += sales_base * (1 - policy.commission_rate)
        payout_queues["low"][payout_day] += sales_low * (1 - policy.commission_rate)
        payout_queues["high"][payout_day] += sales_high * (1 - policy.commission_rate)

        return_day = day + timedelta(days=7)
        returns_queues["base"][return_day] += sales_base * baseline.return_rate
        returns_queues["low"][return_day] += sales_low * baseline.return_rate
        returns_queues["high"][return_day] += sales_high * baseline.return_rate

        inflow_base = payout_queues["base"].pop(day, 0.0)
        inflow_low = payout_queues["low"].pop(day, 0.0)
        inflow_high = payout_queues["high"].pop(day, 0.0)

        procurement = _procurement_spend(
            baseline.avg_procurement,
            day_idx,
            adjustment.procurement_shift_days + policy.procurement_shift_days,
            adjustment.procurement_delta_pct,
        )
        ads = baseline.avg_ads * (1 + adjustment.ads_delta_pct)
        logistics = baseline.avg_logistics * policy.logistics_multiplier
        storage = baseline.avg_storage
        penalty = baseline.avg_penalty
        returns_due_base = returns_queues["base"].pop(day, 0.0)
        returns_due_low = returns_queues["low"].pop(day, 0.0)
        returns_due_high = returns_queues["high"].pop(day, 0.0)

        outflow_base = ads + logistics + storage + penalty + procurement + returns_due_base
        outflow_low = ads + logistics + storage + penalty + procurement + returns_due_low
        outflow_high = ads + logistics + storage + penalty + procurement + returns_due_high

        net_base = inflow_base - outflow_base
        net_low = inflow_low - outflow_low
        net_high = inflow_high - outflow_high

        balance += net_base
        p10_balance += net_low
        p90_balance += net_high

        if balance < min_balance:
            min_balance = balance
            min_balance_date = day

        if p90_balance < 0:
            risk = 0.95
        elif p10_balance < 0:
            risk = 0.6
        else:
            risk = 0.1

        points.append(
            CashflowPoint(
                date=day,
                inflow=round(inflow_base, 2),
                outflow=round(outflow_base, 2),
                net=round(net_base, 2),
                balance=round(balance, 2),
                p10_balance=round(p10_balance, 2),
                p90_balance=round(p90_balance, 2),
                risk_negative=round(risk, 2),
            )
        )

    return SimulationResult(
        points=points,
        min_balance=round(min_balance, 2),
        min_balance_date=min_balance_date,
        ending_balance=round(balance, 2),
    )


def run_forecast(db: Session, request: ForecastRequest) -> ForecastResponse:
    seller_id = resolve_seller_id(db, request.seller_code)
    baseline = _build_baseline(db)
    policy_events = _load_policy_events(db, seller_id)
    policy_by_day = _policy_by_day(policy_events, request.horizon_days)

    simulation = _simulate(
        baseline,
        policy_by_day,
        request.horizon_days,
        request.start_balance,
        SimulationAdjustments(),
    )

    alerts: list[ForecastAlert] = []
    if simulation.min_balance < 0:
        alerts.append(
            ForecastAlert(
                level="high",
                message="Высокий риск кассового разрыва. Проверьте сценарии сокращения расходов и сдвига закупки.",
                alert_date=simulation.min_balance_date,
            )
        )
    elif simulation.min_balance < baseline.avg_daily_sales * 2:
        alerts.append(
            ForecastAlert(
                level="medium",
                message="Запас ликвидности низкий. Желательно подготовить сценарий на случай просадки выплат.",
                alert_date=simulation.min_balance_date,
            )
        )

    return ForecastResponse(
        horizon_days=request.horizon_days,
        start_balance=request.start_balance,
        ending_balance=simulation.ending_balance,
        min_balance=simulation.min_balance,
        min_balance_date=simulation.min_balance_date,
        points=simulation.points,
        alerts=alerts,
    )


def run_scenario(db: Session, request: ScenarioRequest) -> ScenarioResponse:
    seller_id = resolve_seller_id(db, request.seller_code)
    baseline = _build_baseline(db)
    policy_events = _load_policy_events(db, seller_id)
    policy_by_day = _policy_by_day(policy_events, request.horizon_days)

    baseline_simulation = _simulate(
        baseline,
        policy_by_day,
        request.horizon_days,
        request.start_balance,
        SimulationAdjustments(),
    )

    scenario_simulation = _simulate(
        baseline,
        policy_by_day,
        request.horizon_days,
        request.start_balance,
        SimulationAdjustments(
            ads_delta_pct=request.ads_delta_pct,
            price_delta_pct=request.price_delta_pct,
            procurement_shift_days=request.procurement_shift_days,
            procurement_delta_pct=request.procurement_delta_pct,
        ),
    )

    baseline_profit = sum(p.net for p in baseline_simulation.points)
    scenario_profit = sum(p.net for p in scenario_simulation.points)

    if baseline_simulation.min_balance < 0:
        base_risk_score = 1.0
    else:
        base_risk_score = max(0.05, 1.0 - baseline_simulation.min_balance / (abs(baseline_simulation.min_balance) + 10000))

    if scenario_simulation.min_balance < 0:
        scenario_risk_score = 1.0
    else:
        scenario_risk_score = max(0.05, 1.0 - scenario_simulation.min_balance / (abs(scenario_simulation.min_balance) + 10000))

    risk_reduction = max(0.0, base_risk_score - scenario_risk_score)

    recommendation = "Сценарий нейтрален"
    if scenario_simulation.min_balance >= 0 and baseline_simulation.min_balance < 0:
        recommendation = "Сценарий устраняет кассовый разрыв"
    elif risk_reduction > 0.15 and (scenario_profit >= baseline_profit * 0.95):
        recommendation = "Сценарий заметно снижает риск при умеренной потере прибыли"
    elif scenario_profit < baseline_profit * 0.9:
        recommendation = "Сценарий снижает риск, но слишком сильно режет прибыль"

    profit_delta_pct = 0.0
    if abs(baseline_profit) > 1e-6:
        profit_delta_pct = (scenario_profit - baseline_profit) / abs(baseline_profit) * 100

    return ScenarioResponse(
        baseline_min_balance=baseline_simulation.min_balance,
        baseline_min_balance_date=baseline_simulation.min_balance_date,
        scenario_min_balance=scenario_simulation.min_balance,
        scenario_min_balance_date=scenario_simulation.min_balance_date,
        risk_reduction=round(risk_reduction, 4),
        profit_delta_pct=round(profit_delta_pct, 2),
        recommendation=recommendation,
    )


def explain_cashflow(db: Session, seller_code: str = "default") -> ExplainResponse:
    seller_id = resolve_seller_id(db, seller_code)
    baseline = _build_baseline(db)
    events = _load_policy_events(db, seller_id)

    drivers: list[DriverOut] = []

    drivers.append(
        DriverOut(
            driver="Возвраты",
            impact_estimate=round(baseline.return_rate * 100, 2),
            details="Оценка доли возвратов в денежном потоке. Рост возвратов напрямую снижает будущие выплаты.",
        )
    )

    drivers.append(
        DriverOut(
            driver="Реклама",
            impact_estimate=round(baseline.avg_ads, 2),
            details="Средний дневной расход на рекламу в текущей ленте.",
        )
    )

    for event in reversed(events[-5:]):
        if event.event_type == "commission_change_pct":
            drivers.append(
                DriverOut(
                    driver="Изменение комиссии",
                    impact_estimate=event.delta_value or 0.0,
                    details=event.evidence,
                    source_document_id=event.document_id,
                )
            )
        elif event.event_type == "payout_delay_days":
            drivers.append(
                DriverOut(
                    driver="Сдвиг срока выплат",
                    impact_estimate=event.delta_value or 0.0,
                    details=event.evidence,
                    source_document_id=event.document_id,
                )
            )
        elif event.event_type == "logistics_change_pct":
            drivers.append(
                DriverOut(
                    driver="Рост логистики",
                    impact_estimate=event.delta_value or 0.0,
                    details=event.evidence,
                    source_document_id=event.document_id,
                )
            )
        elif event.event_type == "sales_drop_pct":
            drivers.append(
                DriverOut(
                    driver="Просадка продаж из внешнего сигнала",
                    impact_estimate=event.delta_value or 0.0,
                    details=event.evidence,
                    source_document_id=event.document_id,
                )
            )
        elif event.event_type == "procurement_delay_days":
            drivers.append(
                DriverOut(
                    driver="Сдвиг поставки/закупки",
                    impact_estimate=event.delta_value or 0.0,
                    details=event.evidence,
                    source_document_id=event.document_id,
                )
            )

    return ExplainResponse(drivers=drivers[:8])
