from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models import ExternalEvent, ExternalSignalImpact, SellerContextItem, SellerProfile
from app.schemas.context import SignalImpactOut
from app.services.context import ensure_default_seller_context

GLOBAL_POLICY_EVENT_TYPES = {"commission_change_pct", "logistics_change_pct", "payout_delay_days"}
SUPPLY_EVENT_TYPES = {"supply_disruption", "route_blockage", "customs_delay"}


def _extract_country(text: str) -> str | None:
    t = text.lower()
    if any(token in t for token in ("турц", "turkey", "turkiye")):
        return "TR"
    if any(token in t for token in ("росси", "russia", "rf")):
        return "RU"
    return None


def _extract_product_keywords(text: str) -> set[str]:
    t = text.lower()
    out: set[str] = set()
    if any(token in t for token in ("помидор", "томат", "tomato")):
        out.add("tomato")
    if any(token in t for token in ("огурц", "cucumber")):
        out.add("cucumber")
    if any(token in t for token in ("яблок", "apple")):
        out.add("apple")
    return out


def _is_full_route_blockage(text: str) -> bool:
    t = text.lower()
    return any(token in t for token in ("все фуры", "all trucks", "all lorries", "полная остановка"))


def _score_relevance(event: ExternalEvent, context_items: list[SellerContextItem]) -> tuple[str | None, float]:
    if event.event_type in GLOBAL_POLICY_EVENT_TYPES:
        return None, 0.75

    evidence = (event.evidence or "").lower()
    country = _extract_country(evidence)
    products = _extract_product_keywords(evidence)

    best_item_id: str | None = None
    best_score = 0.0

    for item in context_items:
        score = 0.0
        item_keywords = (item.product_keywords or "").lower()

        if products and any(keyword in item_keywords for keyword in products):
            score += 0.55
        if item.category and item.category in evidence:
            score += 0.15
        if country and item.origin_country and item.origin_country.upper() == country:
            score += 0.3
        if item.supplier_name and item.supplier_name in evidence:
            score += 0.1
        if item.route_name and item.route_name in evidence:
            score += 0.1
        if event.event_type in SUPPLY_EVENT_TYPES and _is_full_route_blockage(evidence):
            score += 0.05

        if score > best_score:
            best_score = score
            best_item_id = item.id

    return best_item_id, min(1.0, best_score)


def _translate_event(event: ExternalEvent) -> list[tuple[str, float, dict]]:
    details = {"source_event_type": event.event_type}
    if event.event_type == "commission_change_pct":
        return [("commission_rate_delta_pct", float(event.delta_value or 0.0), details)]
    if event.event_type == "logistics_change_pct":
        return [("logistics_cost_delta_pct", float(event.delta_value or 0.0), details)]
    if event.event_type == "payout_delay_days":
        return [("payout_delay_delta_days", float(event.delta_value or 0.0), details)]
    if event.event_type in SUPPLY_EVENT_TYPES:
        evidence = (event.evidence or "").lower()
        delay_days = float(event.delta_value or 7.0)
        drop_pct = -35.0 if _is_full_route_blockage(evidence) else -20.0
        if any(token in evidence for token in ("помидор", "томат", "tomato")):
            drop_pct -= 5.0
        return [
            ("sales_drop_pct", drop_pct, {"duration_days": 14, "source_event_type": event.event_type}),
            ("procurement_delay_days", delay_days, {"duration_days": 14, "source_event_type": event.event_type}),
        ]
    return []


def apply_event_impacts(db: Session, events: list[ExternalEvent]) -> int:
    if not events:
        return 0

    ensure_default_seller_context(db)

    sellers = db.query(SellerProfile).all()
    contexts = db.query(SellerContextItem).filter(SellerContextItem.is_active.is_(True)).all()
    context_by_seller: dict[str, list[SellerContextItem]] = {}
    for item in contexts:
        context_by_seller.setdefault(item.seller_id, []).append(item)

    created = 0
    for event in events:
        translated = _translate_event(event)
        if not translated:
            continue

        for seller in sellers:
            item_id, score = _score_relevance(event, context_by_seller.get(seller.id, []))
            is_relevant = score >= 0.6
            if event.event_type in GLOBAL_POLICY_EVENT_TYPES:
                is_relevant = True

            for impact_type, impact_value, details in translated:
                impact = ExternalSignalImpact(
                    external_event_id=event.id,
                    seller_id=seller.id,
                    context_item_id=item_id,
                    is_relevant=is_relevant,
                    relevance_score=score,
                    impact_type=impact_type,
                    impact_value=impact_value,
                    effective_date=event.effective_date or date.today(),
                    details=details,
                    evidence=event.evidence,
                )
                db.add(impact)
                created += 1

    db.commit()
    return created


def list_signal_impacts(
    db: Session,
    *,
    seller_id: str | None = None,
    limit: int = 100,
    relevant_only: bool = True,
) -> list[SignalImpactOut]:
    query = db.query(ExternalSignalImpact)
    if seller_id:
        query = query.filter(ExternalSignalImpact.seller_id == seller_id)
    if relevant_only:
        query = query.filter(ExternalSignalImpact.is_relevant.is_(True))

    rows = (
        query.order_by(ExternalSignalImpact.effective_date.desc(), ExternalSignalImpact.created_at.desc())
        .limit(limit)
        .all()
    )
    return [SignalImpactOut.model_validate(row) for row in rows]
