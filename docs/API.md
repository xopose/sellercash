# API SellerCash (Architecture-Aligned MVP)

Base URL:

```text
http://localhost:8000/api/v1
```

## 1. Health

### GET `/health`

Проверка доступности API.

Response:

```json
{"status":"ok"}
```

## 2. Finance Core

### POST `/finance/import`

Импорт финансовой ленты из `CSV/XLSX` в таблицу `finance_events`.

`multipart/form-data`:

- `file` - файл с колонками: `date`, `event_type`, `amount`, `status` (опционально), `source` (опционально)

### GET `/finance/events?limit=100`

Список последних нормализованных денежных событий.

## 3. Seller Context Layer

### POST `/context/items`

Добавление карточки контекста селлера (SKU/страна/маршрут/поставщик).

Request:

```json
{
  "seller_code": "default",
  "seller_name": "Default Seller",
  "sku": "tomato_tr",
  "category": "vegetables",
  "origin_country": "TR",
  "supplier_name": "turkey_supplier",
  "route_name": "tr-ru-road",
  "product_keywords": "tomato,помидор,томаты",
  "is_active": true
}
```

### GET `/context/items?seller_code=default`

Чтение context-профиля селлера.

## 4. Forecast & Scenario Engine

### POST `/cashflow/forecast`

Базовый прогноз денежного остатка с учетом:

- финансовой истории,
- релевантных `external_signal_impacts`,
- лагов выплат и возвратов.

Request:

```json
{
  "seller_code": "default",
  "horizon_days": 60,
  "start_balance": 150000
}
```

### POST `/cashflow/scenario`

What-if сценарий с управляемыми рычагами.

Request:

```json
{
  "seller_code": "default",
  "horizon_days": 60,
  "start_balance": 150000,
  "ads_delta_pct": -0.15,
  "price_delta_pct": 0.03,
  "procurement_shift_days": 7,
  "procurement_delta_pct": -0.1
}
```

### GET `/cashflow/explain?seller_code=default`

Драйверы изменения прогноза с привязкой к evidence.

## 5. Knowledge & Signals Layer

### POST `/knowledge/documents/upload`

Загрузка документа (`pdf/txt/html`) и запуск цепочки:

`document -> chunks -> search index -> external events -> seller impacts`.

`multipart/form-data`:

- `file` - документ
- `source_url` (optional) - URL первоисточника

Response:

```json
{
  "document_id": "...",
  "source_name": "rules_may.pdf",
  "chunks_indexed": 42,
  "events_extracted": 5,
  "impacts_created": 11
}
```

### POST `/knowledge/documents/from-url`

Индексация документа напрямую по URL.

Request:

```json
{
  "url": "https://example.com/marketplace-rules"
}
```

### POST `/knowledge/signals/ingest`

Webhook для внешних систем (например Interfax feed adapter).
Внешний сигнал конвертируется в текстовый документ, индексируется и участвует в расчете cashflow.

Request:

```json
{
  "source_system": "interfax",
  "title": "На границе с Турцией задержаны все фуры с помидорами",
  "body": "Ожидаемая задержка поставки 10 дней. Риск дефицита в ближайшие 2 недели.",
  "source_url": "https://example.org/news/123",
  "published_at": "2026-03-30T09:10:00Z",
  "tags": ["logistics", "tomato", "turkey"]
}
```

### GET `/knowledge/search?q=комиссия&top_k=5`

BM25-поиск по индексированным фрагментам.

### GET `/knowledge/events?limit=100`

Извлеченные структурированные события (`external_events`).

### GET `/knowledge/impacts?seller_code=default&limit=100&relevant_only=true`

Сигналы, которые прошли relevance-проверку и были трансформированы в параметры финансовой модели.
