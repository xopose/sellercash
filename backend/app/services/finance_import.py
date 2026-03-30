from __future__ import annotations

from io import BytesIO

import pandas as pd
from sqlalchemy.orm import Session

from app.models import FinanceEvent
from app.schemas.finance import FinanceImportResult

COLUMN_ALIASES = {
    "event_date": ["event_date", "date", "дата", "day"],
    "event_type": ["event_type", "type", "тип", "категория", "operation"],
    "amount": ["amount", "sum", "сумма", "value"],
    "status": ["status", "статус"],
    "source": ["source", "источник"],
    "currency": ["currency", "валюта"],
}


def _pick_column(columns: list[str], aliases: list[str]) -> str | None:
    lowered = {c.lower().strip(): c for c in columns}
    for alias in aliases:
        original = lowered.get(alias.lower())
        if original:
            return original
    return None


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapped: dict[str, str] = {}
    columns = list(df.columns)
    for target, aliases in COLUMN_ALIASES.items():
        picked = _pick_column(columns, aliases)
        if picked:
            mapped[target] = picked

    required = {"event_date", "event_type", "amount"}
    if not required.issubset(mapped.keys()):
        missing = ", ".join(sorted(required - set(mapped.keys())))
        raise ValueError(f"Finance file is missing required columns: {missing}")

    out = pd.DataFrame()
    out["event_date"] = pd.to_datetime(df[mapped["event_date"]], errors="coerce", dayfirst=True)
    out["event_type"] = df[mapped["event_type"]].astype(str).str.strip().str.lower()
    out["amount"] = pd.to_numeric(df[mapped["amount"]], errors="coerce")
    out["status"] = df[mapped["status"]].astype(str).str.strip().str.lower() if "status" in mapped else "fact"
    out["source"] = df[mapped["source"]].astype(str).str.strip() if "source" in mapped else None
    out["currency"] = df[mapped["currency"]].astype(str).str.strip().str.upper() if "currency" in mapped else "RUB"
    return out


def _read_table(content: bytes, filename: str) -> pd.DataFrame:
    lower = filename.lower()
    if lower.endswith(".csv"):
        return pd.read_csv(BytesIO(content))
    if lower.endswith(".xls") or lower.endswith(".xlsx"):
        return pd.read_excel(BytesIO(content))
    raise ValueError("Unsupported file type. Please use CSV or Excel")


def import_finance_file(*, file_content: bytes, filename: str, db: Session) -> FinanceImportResult:
    raw_df = _read_table(file_content, filename)
    df = _normalize_columns(raw_df)

    imported = 0
    skipped = 0
    by_type: dict[str, int] = {}

    for row in df.itertuples(index=False):
        if pd.isna(row.event_date) or pd.isna(row.amount):
            skipped += 1
            continue

        status = row.status if isinstance(row.status, str) and row.status else "fact"
        source = row.source if isinstance(row.source, str) and row.source and row.source != "None" else filename
        currency = row.currency if isinstance(row.currency, str) and row.currency else "RUB"

        event = FinanceEvent(
            event_date=row.event_date.date(),
            event_type=str(row.event_type),
            amount=float(row.amount),
            status=status,
            source=source,
            currency=currency,
        )
        db.add(event)
        imported += 1
        by_type[event.event_type] = by_type.get(event.event_type, 0) + 1

    db.commit()
    return FinanceImportResult(imported_rows=imported, skipped_rows=skipped, by_type=by_type)
