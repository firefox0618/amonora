# PROJECT_CONTEXT.md

## Project summary
Amonora — экосистема цифровых сервисов.
Текущий продукт: Telegram-first VPN-сервис с клиентским путём через `@amonora_bot`.

## Main system contours
- `bot` — primary user entry point
- `support_bot` — support flows
- `control_bot` — internal notifications + admin operations
- `landing` — public web surface
- `dashboard` — admin backend/API
- `dashboard/ui` — admin frontend (Next.js)
- `backend` — shared domain logic, models, core
- `PostgreSQL` — primary source of truth
- `ops` — deployment/runtime/infrastructure

## Current architectural reality
Код не полностью нормализован. Доменная логика распределена между:
- `backend`
- `bot`
- `dashboard`
- `support_bot`

Это ожидаемо и должно учитываться при изменениях.

## Key transition areas
- `dashboard` и `dashboard/ui` сосуществуют
- `docs` папки больше нет — все документы в `documentation/`

## Priority goals
1. Сохранять рабочую функциональность
2. Улучшать ясность структуры
3. Снижать архитектурную неоднозначность
4. Делать изменения безопасными для людей и AI
5. Работать маленькими задачами, а не широкими рефакторингами
