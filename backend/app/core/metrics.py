from __future__ import annotations

from prometheus_client import Counter

forecast_requests_total = Counter(
    "sellercash_forecast_requests_total",
    "Total number of baseline cashflow forecast requests",
)

scenario_requests_total = Counter(
    "sellercash_scenario_requests_total",
    "Total number of what-if scenario requests",
)

context_items_created_total = Counter(
    "sellercash_context_items_created_total",
    "Total number of seller context items created",
)

finance_imports_total = Counter(
    "sellercash_finance_imports_total",
    "Total number of finance import operations",
)

documents_uploaded_total = Counter(
    "sellercash_documents_uploaded_total",
    "Total number of indexed knowledge documents",
)

signals_ingested_total = Counter(
    "sellercash_signals_ingested_total",
    "Total number of external signals ingested",
)
