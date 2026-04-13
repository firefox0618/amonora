# TASK 146 — Node alert stability tuning

Дата: 31 марта 2026

## Контекст

- В control flow приходят частые `Нода деградирует` для `Amonora Germany Primary`, хотя live-метрики в момент проверки нормальные.
- `amonora-server-watchdog` опрашивает ноды каждую минуту и сам создаёт заметную служебную нагрузку на core-host.
- Отдельный 5-минутный путь `ops/control_error_triggers.py` тоже умеет открывать node-инциденты по единичным warning-снимкам, из-за чего появляются короткие шумовые алерты.

## Scope

- Снизить шум node-alerts без потери реальных `down`/critical инцидентов.
- Уменьшить частоту и стоимость node polling.
- Не менять автоматически размещение пользователей по регионам, если live-данные не подтверждают реальную перегрузку.

## План

1. Ослабить warning-only node incidents в `control_error_triggers`.
2. Сделать `server_watchdog` менее агрессивным по частоте и по подтверждению деградации.
3. Поднять read-cache TTL на server/overview snapshot путях dashboard.
4. Проверить таргетными unit tests и затем выкатить на прод.
