from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.context import SellerContextItemCreate, SellerContextItemOut
from app.services.context import add_context_item, ensure_default_seller_context, list_context_items

router = APIRouter(prefix="/context", tags=["context"])


@router.post("/items", response_model=SellerContextItemOut)
def create_context_item(
    request: SellerContextItemCreate,
    db: Session = Depends(get_db),
) -> SellerContextItemOut:
    return add_context_item(db, request)


@router.get("/items", response_model=list[SellerContextItemOut])
def get_context_items(
    seller_code: str = Query(default="default"),
    db: Session = Depends(get_db),
) -> list[SellerContextItemOut]:
    if seller_code.strip().lower() == "default":
        ensure_default_seller_context(db)
    return list_context_items(db, seller_code=seller_code)
