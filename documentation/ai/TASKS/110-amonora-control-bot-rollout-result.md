# TASK 110 — Amonora Control Bot Rollout Result

## Result
Completed.

`Amonora Control` now exists as a separate internal Telegram bot and event-dispatch layer for operational/system notifications, while `@amonora_support_bot` is kept focused on client tickets, media, assignment, and replies.

## What changed

- Added a new polling service:
  - `control_bot`
- Added a central event log table:
  - `control_notification_events`
- Routed internal/system notifications into `Amonora Control`:
  - manual payment review
  - dashboard login codes
  - watchdog/node alerts
  - user lifecycle events
  - access/key delivery and reprovision events
  - system/payment/access failures
- Removed payment review UI/actions from `support_bot`.
- Added allowlist role model for control admins:
  - `owner`
  - `admin`
  - `operator`
  - `support-view-only`
- Added control-bot command/UI surface:
  - `/start`
  - `/status`
  - `/nodes`
  - `/payments`
  - `/users`
  - `/alerts`
  - `/login_codes`
  - `/help`
- Added payment review actions in `Amonora Control`:
  - confirm
  - reject
  - open user in dashboard
  - open payment in dashboard
- Changed dashboard auth-code delivery hint from `@amonora_support_bot` to `@amonora_control_bot`.
- Added cooldown/dedupe-aware delivery for repeated alerts and explicit recovery events.
- Added nightly critical-only mode and a daily-summary loop behind env flags.
- Hardened callback rendering in `control_bot` so repeated presses on the same screen do not spam logs with `message is not modified`.

## Routing split after rollout

### Amonora Control

- new manual payment requests
- manual payment confirm/reject
- payment activation success/failure chain events
- dashboard login-code delivery
- node offline/degraded/overloaded/recovered alerts
- user created / trial started / subscription activated / extended
- key issued / reprovisioned / provisioning failure
- system/access/payment errors

### Support Bot

- inbound user tickets
- photos, videos, documents, screenshots
- ticket assignment / transfer / close
- operator replies to users

## Validation

### Tests

- `./venv/bin/python -m unittest -q tests.test_control_dispatcher tests.test_control_queries tests.test_control_router tests.test_dashboard_auth_session`
- `./venv/bin/python -m unittest -q tests.test_payment_finalization tests.test_confirm_external_payment_record tests.test_support_storage tests.test_dashboard_support_attachment tests.test_dashboard_api_v2_support_contract`
- `./venv/bin/python -m unittest -q tests.test_access_reminders tests.test_dashboard_system_alerts tests.test_dashboard_api_v2_contract tests.test_bot_copy_updates tests.test_bot_devices_ui tests.test_device_region_change_guard`

### Static checks

- `python3 -m compileall control_bot support_bot dashboard bot backend ops tests documentation`
- `python3 -m json.tool documentation/manifest.json`
- `git diff --check`

## Runtime notes

- `Amonora Control` is deployed as a separate systemd service:
  - `amonora-control-bot.service`
- Delivery defaults to direct messages for allowed control-admin Telegram IDs.
- Telegram DM delivery requires each control admin to open `@amonora_control_bot` and press `/start` at least once.
- Dashboard auth-code history stores masked codes; plaintext codes are only sent in the live Telegram message.

## Files of note

- `control_bot/main.py`
- `control_bot/router.py`
- `control_bot/queries.py`
- `control_bot/dispatcher.py`
- `control_bot/access.py`
- `backend/core/models.py`
- `bot/db.py`
- `bot/payment_flow.py`
- `bot/manual_payments.py`
- `bot/handlers/devices.py`
- `dashboard/main.py`
- `dashboard/services.py`
- `support_bot/router.py`
- `ops/server_watchdog.py`
- `ops/access_reminders.py`
- `ops/systemd/amonora-control-bot.service`

## Follow-up note

The rollout keeps existing payment/domain tables intact and layers the new event log on top, so the support/control split improves operational clarity without forcing a risky broad rename/refactor through the whole ecosystem.
