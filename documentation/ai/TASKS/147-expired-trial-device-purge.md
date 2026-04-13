# TASK 147 — Expired trial device purge

Дата: 31 марта 2026

## Контекст

- После истечения пробного периода часть пользователей всё ещё видит рабочий VPN-сеанс.
- Live audit показал, что на нодах expired-trial клиенты уже в основном disabled или absent, но DB-устройства всё ещё сохраняются, а established sessions могут доживать дольше ожидаемого.

## Scope

- Для `trial-only expired` пользователей не только отзывать доступ, но и удалять VPN-устройства.
- Не затрагивать бывших платящих пользователей с истёкшей подпиской.
- После rollout вручную прогнать purge и перепроверить остатки в БД.

## Acceptance

- expired-trial users without paid subscription no longer keep `vpn_clients` rows;
- worker retries failed purges safely;
- targeted tests cover purge selection and idempotency.
