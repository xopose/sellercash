from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import FinanceEvent
from app.schemas.finance import FinanceEventOut, FinanceImportResult
from app.services.finance_import import import_finance_file

router = APIRouter(prefix="/finance", tags=["finance"])


@router.post("/import", response_model=FinanceImportResult)
async def import_finance(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> FinanceImportResult:
    content = await file.read()
    try:
        return import_finance_file(file_content=content, filename=file.filename or "upload.csv", db=db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/events", response_model=list[FinanceEventOut])
def list_finance_events(
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[FinanceEventOut]:
    rows = db.query(FinanceEvent).order_by(FinanceEvent.event_date.desc()).limit(limit).all()
    return [FinanceEventOut.model_validate(row) for row in rows]
