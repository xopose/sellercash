## Цель

Показать, что SellerCash:

1. строит cashflow-прогноз по финансовой ленте;
2. принимает внешний сигнал из интернет-источника;
3. проверяет релевантность сигнала конкретному селлеру;
4. пересчитывает риск кассового разрыва;
5. предлагает управленческий сценарий.

## Шаги

### Шаг 1. Baseline без внешнего шока

1. Открыть `http://localhost:8000`.
2. Загрузить финансовую выгрузку через `POST /api/v1/finance/import`.
3. Выполнить `POST /api/v1/cashflow/forecast`:

```json
{
  "seller_code": "default",
  "horizon_days": 60,
  "start_balance": 150000
}
```

4. Зафиксировать `min_balance` и `min_balance_date`.

### Шаг 2. Проверка seller context

Вызвать:

```text
GET /api/v1/context/items?seller_code=default
```

Убедиться, что в профиле есть контекст по томатам из Турции (`origin_country=TR`).

### Шаг 3. Подача внешнего сигнала (Interfax-like)

Вызвать:

```text
POST /api/v1/knowledge/signals/ingest
```

Пример payload:

```json
{
  "source_system": "interfax",
  "title": "На границе с Турцией задержаны все фуры с помидорами",
  "body": "Ожидаемая задержка поставки 10 дней. Риск дефицита в ближайшие 2 недели.",
  "tags": ["logistics", "tomato", "turkey"]
}
```

Проверить:

- `GET /api/v1/knowledge/events`
- `GET /api/v1/knowledge/impacts?seller_code=default`

Ожидаемо появятся impacts:

- `sales_drop_pct`
- `procurement_delay_days`

### Шаг 4. Пересчет cashflow после сигнала

Повторно выполнить `POST /api/v1/cashflow/forecast` и сравнить с baseline.

Дополнительно вызвать:

```text
GET /api/v1/cashflow/explain?seller_code=default
```

Показать связь: `источник -> событие -> параметр модели -> эффект на cashflow`.

### Шаг 5. Сценарий управления

Выполнить `POST /api/v1/cashflow/scenario`:

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

Оценить:

- снижение риска ухода в минус (`risk_reduction`);
- изменение прибыли (`profit_delta_pct`);
- итоговую рекомендацию.
