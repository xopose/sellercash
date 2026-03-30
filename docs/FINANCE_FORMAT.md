# Формат финансовой выгрузки

Поддерживаемые форматы: `CSV`, `XLS`, `XLSX`.

## Обязательные колонки

Нужны минимум три поля (в любом из поддержанных алиасов):

- Дата события:
  - `event_date`, `date`, `дата`, `day`
- Тип события:
  - `event_type`, `type`, `тип`, `категория`, `operation`
- Сумма:
  - `amount`, `sum`, `сумма`, `value`

## Необязательные колонки

- `status` / `статус` (`fact` или `forecast`, по умолчанию `fact`)
- `source` / `источник`
- `currency` / `валюта` (по умолчанию `RUB`)

## Типовые значения `event_type`

- `sale` / `продажа`
- `return` / `возврат`
- `ads` / `реклама`
- `logistics` / `логистика`
- `storage` / `хранение`
- `penalty` / `штраф`
- `procurement` / `закупка`

## Пример CSV

```csv
date,type,amount,status
2026-02-01,sale,12000,fact
2026-02-01,ads,-1100,fact
2026-02-03,return,-900,fact
2026-02-04,logistics,-650,fact
2026-02-09,procurement,-20000,fact
```
