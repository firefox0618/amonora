# TASK 147 — Expired trial device purge result

Дата: 31 марта 2026

## Что сделано

- В `ops/access_reminders.py` добавлен отдельный purge-path для `trial-only expired` пользователей:
  - сначала старый revoke-path отключает доступ;
  - затем worker удаляет remote VPN device state;
  - после успешного remote delete удаляется и `vpn_clients` запись из БД.
- Purge не применяется к бывшим платящим пользователям, у которых уже была `subscription_expires_at`.
- Добавлен таргетный unit test на purge selection и идемпотентность.

## Ожидаемый эффект

- После окончания trial у пользователя не остаётся live device record, который мог поддерживать старые подключения или путать дальнейшую диагностику.
- Повторные прогоны worker’а безопасны: успешно очищенные trial-only пользователи больше не обрабатываются.

## Validation

- `./venv/bin/python -m py_compile ops/access_reminders.py tests/test_expired_access_revocation.py`
- `./venv/bin/python -m unittest tests.test_expired_access_revocation tests.test_access_reminders`
