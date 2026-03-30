# Архитектура SellerCash

## 1. Логические слои

### 1.1 Financial Core

- Импорт: `CSV/XLSX -> finance_events`.
- Нормализация в единый формат денежного события.
- Календарь cashflow по дням.

### 1.2 Seller Context Layer

Хранит контекст конкретного бизнеса:

- SKU/категория;
- страна происхождения;
- поставщик;
- маршрут поставки;
- ключевые слова по товару.

Без этого слоя внешняя новость не может быть корректно классифицирована как релевантная или нерелевантная.

### 1.3 Knowledge & Signals Layer (Lucene)

- Документы и новости индексируются в OpenSearch (Lucene).
- Поиск: BM25 по фрагментам.
- Event Extraction: извлечение структурных событий из текста.
- Поддерживаемые классы событий в MVP:
  - `commission_change_pct`
  - `logistics_change_pct`
  - `payout_delay_days`
  - `supply_disruption`

### 1.4 Relevance + Parameter Translation

После извлечения события:

1. `Relevance Engine` сопоставляет событие с seller context.
2. `Parameter Translation` преобразует событие в влияние на модель cashflow.

Таблица результата: `external_signal_impacts`.

Примеры трансляции:

- `commission_change_pct` -> `commission_rate_delta_pct`
- `payout_delay_days` -> `payout_delay_delta_days`
- `supply_disruption` -> `sales_drop_pct` + `procurement_delay_days`

### 1.5 Forecast & Scenario Engine

- Прогнозирует cashflow на горизонте 7-120 дней.
- Учитывает лаги выплат, возвраты, удержания, закупки.
- Подхватывает релевантные внешние impacts и изменяет параметры симуляции.
- Сценарный блок оценивает рычаги (реклама, цена, закупка).
- Explainability возвращает драйверы прогноза и evidence.

## 2. Внешние источники (включая Interfax-подобные системы)

Система поддерживает три канала поступления внешнего сигнала:

- загрузка файла: `POST /knowledge/documents/upload`;
- загрузка по URL: `POST /knowledge/documents/from-url`;
- webhook внешней системы: `POST /knowledge/signals/ingest`.

Webhook-канал позволяет принимать структурированный поток из внешней системы мониторинга новостей/инцидентов.

## 3. Сквозной сценарий: томаты из Турции

1. В `seller_context_items` есть карточка SKU томатов с происхождением `TR`.
2. Во внешнем потоке приходит сообщение: "на границе с Турцией задержаны все фуры с помидорами, задержка 10 дней".
3. Extractor фиксирует `supply_disruption`.
4. Relevance Engine подтверждает релевантность селлеру.
5. Translation создает impacts:
   - `sales_drop_pct`
   - `procurement_delay_days`
6. Forecast пересчитывает cashflow и может сдвинуть дату кассового разрыва.
7. Explain показывает источник и влияние.

## 4. Физические компоненты (Docker Compose)

- `api` (FastAPI + SQLAlchemy)
- `postgres` (финансы, документы, события, impacts, seller context)
- `opensearch` (Lucene index)
- `minio` (сырой контент документов)
- `minio-init` (инициализация bucket)

## 5. Диаграмма

PUML-версия хранится в `docs/architecture.puml`.
