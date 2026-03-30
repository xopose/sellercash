from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import SellerContextItem, SellerProfile
from app.schemas.context import SellerContextItemCreate, SellerContextItemOut

DEFAULT_SELLER_CODE = "default"
DEFAULT_SELLER_NAME = "Default Seller"


def _normalize_country(value: str | None) -> str | None:
    if value is None:
        return None
    clean = value.strip().upper()
    if not clean:
        return None

    aliases = {
        "ТУРЦИЯ": "TR",
        "TURKEY": "TR",
        "TURKIYE": "TR",
        "TR": "TR",
        "РОССИЯ": "RU",
        "RUSSIA": "RU",
        "RF": "RU",
        "RU": "RU",
    }
    return aliases.get(clean, clean)


def get_or_create_seller(db: Session, *, code: str, name: str) -> SellerProfile:
    seller = db.query(SellerProfile).filter(SellerProfile.code == code).first()
    if seller:
        return seller

    seller = SellerProfile(code=code, name=name)
    db.add(seller)
    db.flush()
    return seller


def ensure_default_seller_context(db: Session) -> SellerProfile:
    seller = get_or_create_seller(db, code=DEFAULT_SELLER_CODE, name=DEFAULT_SELLER_NAME)
    existing = (
        db.query(SellerContextItem)
        .filter(SellerContextItem.seller_id == seller.id)
        .filter(SellerContextItem.is_active.is_(True))
        .count()
    )
    if existing:
        db.commit()
        return seller

    demo_item = SellerContextItem(
        seller_id=seller.id,
        sku="tomato_tr",
        category="vegetables",
        origin_country="TR",
        supplier_name="turkey_supplier",
        route_name="TR-RU-road",
        product_keywords="tomato,помидор,томаты",
        is_active=True,
    )
    db.add(demo_item)
    db.commit()
    return seller


def add_context_item(db: Session, payload: SellerContextItemCreate) -> SellerContextItemOut:
    seller = get_or_create_seller(db, code=payload.seller_code.strip().lower(), name=payload.seller_name.strip())
    item = SellerContextItem(
        seller_id=seller.id,
        sku=payload.sku.strip(),
        category=payload.category.strip().lower() if payload.category else None,
        origin_country=_normalize_country(payload.origin_country),
        supplier_name=payload.supplier_name.strip().lower() if payload.supplier_name else None,
        route_name=payload.route_name.strip().lower() if payload.route_name else None,
        product_keywords=payload.product_keywords.strip().lower() if payload.product_keywords else None,
        is_active=payload.is_active,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return SellerContextItemOut.model_validate(item)


def list_context_items(db: Session, seller_code: str = DEFAULT_SELLER_CODE) -> list[SellerContextItemOut]:
    seller = db.query(SellerProfile).filter(SellerProfile.code == seller_code.strip().lower()).first()
    if not seller:
        return []

    rows = (
        db.query(SellerContextItem)
        .filter(SellerContextItem.seller_id == seller.id)
        .order_by(SellerContextItem.created_at.desc())
        .all()
    )
    return [SellerContextItemOut.model_validate(row) for row in rows]


def resolve_seller_id(db: Session, seller_code: str | None) -> str:
    code = (seller_code or DEFAULT_SELLER_CODE).strip().lower()
    seller = db.query(SellerProfile).filter(SellerProfile.code == code).first()
    if seller:
        return seller.id
    seller = ensure_default_seller_context(db)
    return seller.id
