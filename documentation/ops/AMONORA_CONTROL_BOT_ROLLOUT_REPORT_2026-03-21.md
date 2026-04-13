# Amonora Control Bot Rollout Report — 2026-03-21

## Summary

Completed:

- `Amonora Control` is now the dedicated internal Telegram bot for operational/system notifications and admin-side review.
- `Support Bot` is now limited to client support cases, tickets, media, assignment, and replies.
- Internal payment/auth/node/access/system events now go through a centralized dispatcher and typed event log.
- Dashboard login-code delivery now points to `@amonora_control_bot`.

## Delivered components

### New runtime/service

- new package:
  - `control_bot`
- new systemd unit:
  - `amonora-control-bot.service`

### New data/event layer

- central event log table:
  - `control_notification_events`

### New admin command surface

- `/start`
- `/status`
- `/nodes`
- `/payments`
- `/users`
- `/alerts`
- `/login_codes`
- `/help`

### New control roles

- `owner`
- `admin`
- `operator`
- `support-view-only`

## Routing split

### Routed into Amonora Control

- new manual payment requests
- manual payment confirm/reject
- payment activation success
- payment/access chain failures
- dashboard login codes
- node offline/degraded/overloaded/recovered alerts
- new user
- trial started
- paid subscription activated
- subscription extended
- key issued
- key re-issued / reprovision
- node change
- provisioning/access failures
- system errors

### Kept in Support Bot

- user text messages
- user photos/videos/documents/screenshots
- ticket assignment/transfer/close
- operator replies
- support statuses

## Notification model

Categories:

- `payments`
- `nodes`
- `users`
- `access`
- `panel_auth`
- `errors`
- `system`

Severity:

- `INFO`
- `WARNING`
- `CRITICAL`

Persistence:

- title/body
- category/severity
- entity reference
- payload JSON
- dedupe key
- first created time
- last sent time
- repeat count
- resolve time for recovered incidents

Rules:

- repeated identical alerts respect cooldown
- recovery is emitted as a separate event
- masked auth codes are stored in history
- plaintext auth codes live only in the live Telegram message

## Environment variables

- `AMONORA_CONTROL_BOT_TOKEN`
- `AMONORA_CONTROL_ALLOWED_TELEGRAM_IDS`
- `AMONORA_CONTROL_OWNER_IDS`
- `AMONORA_CONTROL_ADMIN_IDS`
- `AMONORA_CONTROL_OPERATOR_IDS`
- `AMONORA_CONTROL_SUPPORT_VIEW_ONLY_IDS`
- `AMONORA_CONTROL_CHAT_IDS`
- `AMONORA_CONTROL_ENABLE_PAYMENTS`
- `AMONORA_CONTROL_ENABLE_NODES`
- `AMONORA_CONTROL_ENABLE_USERS`
- `AMONORA_CONTROL_ENABLE_ACCESS`
- `AMONORA_CONTROL_ENABLE_PANEL_AUTH`
- `AMONORA_CONTROL_ENABLE_ERRORS`
- `AMONORA_CONTROL_ENABLE_SYSTEM`
- `AMONORA_CONTROL_DEFAULT_COOLDOWN_SECONDS`
- `AMONORA_CONTROL_INFRA_COOLDOWN_SECONDS`
- `AMONORA_CONTROL_NIGHT_CRITICAL_ONLY`
- `AMONORA_CONTROL_NIGHT_HOURS`
- `AMONORA_CONTROL_DAILY_SUMMARY_ENABLED`
- `AMONORA_CONTROL_DAILY_SUMMARY_HOUR`
- `DASHBOARD_PUBLIC_BASE_URL`

## Example messages

### Payment

`INFO · Новая оплата`

- Пользователь: `@username`
- Сумма: `299 ₽`
- Метод: `СБП`
- Статус: `ожидает подтверждения`

### Access activated

`INFO · Доступ активирован`

- Пользователь: `@username`
- План: `30 дней`
- Нода: `Germany`

### Panel auth

`INFO · Код входа в панель`

- Пользователь: `admin`
- Код: `482***`
- TTL: `10 минут`

### Node issue

`WARNING · Нода недоступна`

- Регион: `Denmark`
- Статус: `offline`
- Причина: `health-check timeout`

### Critical

`CRITICAL · Ошибка выдачи ключа`

- Пользователь: `@username`
- Нода: `Denmark`
- Причина: `provisioning failed`

## Validation results

### Automated

- dispatcher / dedupe / masked auth-code tests: passed
- control query / role gating tests: passed
- control router repeat-render regression test: passed
- dashboard auth-session tests: passed
- payment finalization regressions: passed
- support storage + attachment regressions: passed
- dashboard support contract regressions: passed
- access reminder + system alerts regressions: passed
- dashboard API v2 contract regressions: passed
- device/bot flow regressions: passed

### Production/runtime

- `amonora-bot.service`: active
- `amonora-support-bot.service`: active
- `amonora-dashboard.service`: active
- `amonora-control-bot.service`: active
- dashboard backend responds on `127.0.0.1:8088`
- `support_bot` no longer exposes payment review commands/callbacks
- `Amonora Control` Telegram delivery verified for owner and tech-admin

### Operational note

Telegram direct-message delivery still requires each allowed control admin to open `@amonora_control_bot` and press `/start`.

At rollout time:

- owner `7650618403`: delivery verified
- tech-admin `548589949`: delivery verified
- operator `5487345316`: must open the bot to enable DM delivery

## Completion Table

| Пункт | Статус | Что сделано | Доказательство |
|---|---|---|---|
| Separate control bot service | Выполнено | Добавлен `control_bot` и отдельный `systemd` unit | `control_bot/*`, `ops/systemd/amonora-control-bot.service`, runtime service active |
| Central dispatcher and event log | Выполнено | Введён `control_notification_events` и общий dispatcher | `backend/core/models.py`, `control_bot/dispatcher.py` |
| Payments moved out of support bot | Выполнено | Review manual payments удалён из `support_bot` и доступен в `Amonora Control` | `support_bot/router.py`, `control_bot/router.py` |
| Dashboard auth codes moved to control bot | Выполнено | `/dashboard/api/v2/auth/request-code` отправляет в `@amonora_control_bot` | `dashboard/main.py`, auth session tests |
| Node and infra alerts routed to control bot | Выполнено | watchdog / access reminders создают control events | `ops/server_watchdog.py`, `ops/access_reminders.py` |
| User/access lifecycle events routed | Выполнено | user/trial/subscription/key events создают control events | `bot/db.py`, `bot/handlers/devices.py`, `dashboard/services.py` |
| Role-based access control | Выполнено | allowlist + roles `owner/admin/operator/support-view-only` | `control_bot/access.py`, control query tests |
| Admin command set | Выполнено | `/start`, `/status`, `/nodes`, `/payments`, `/users`, `/alerts`, `/login_codes`, `/help` | `control_bot/router.py`, `control_bot/queries.py` |
| Alert cooldown / dedupe / recovery | Выполнено | повторные события не спамят чаще cooldown, recovery отдельный | `control_bot/dispatcher.py`, dispatcher tests |
| Support bot remains client-only | Выполнено | support оставлен для user tickets/media/replies | `support_bot/router.py`, support regressions |
| Docs and knowledge publication | Выполнено | docs + manifest + этот report обновлены | `documentation/*`, `documentation/manifest.json` |

## Transfer checklist

Transferred from support-side admin flow to `Amonora Control`:

- manual payment queue
- manual payment confirm/reject
- dashboard login-code delivery
- node infra alerts
- access/system failure alerts
- user/access lifecycle notifications

Not transferred and intentionally left in `Support Bot`:

- user tickets
- media attachments
- assignment workflows
- operator replies
- ticket status handling
