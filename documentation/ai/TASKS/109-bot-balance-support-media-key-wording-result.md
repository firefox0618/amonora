# TASK 109 — Bot Balance, Support Media, and Key Wording Hardening Result

## Result
Completed.

The bot now uses balance-based referral rewards in rubles, applies that balance safely in RUB payment flows, preserves support media as real Telegram attachments, and consistently calls URI-based access data a `ключ` instead of a `конфиг`.

## What changed

- iOS onboarding now points to the new `Happ` App Store page:
  - `https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973`
- Mobile import copy for `VLESS` / `Trojan` now uses one unified `скачать приложение -> скопировать ключ -> добавить ключ -> пользоваться` flow.
- User-facing bot wording now distinguishes:
  - `Получить ключ` for `VLESS` / `Trojan`
  - `Получить конфиг` for `WireGuard`
- The referral system now credits ruble balance instead of bonus days:
  - `1` qualified paid referral = `50 р`
  - historical already-rewarded referrals are migrated once and idempotently into balance
- The bot home screen and referral section now show:
  - total `Баланс`
  - available-to-spend amount
- RUB payment flows now automatically use balance:
  - reserve on payment creation
  - apply on confirm
  - release on cancel / reject / expire
  - full-balance activation path without an external payment
- `Telegram Stars` remain separate and never spend balance.
- Support tickets now persist Telegram attachment metadata:
  - `file_id`
  - kind
  - filename
  - mime type
  - size
- Support media from users are now copied to admins as real Telegram attachments instead of preview-only text.
- Dashboard and `dashboard_v2` can now open support attachments through:
  - `GET /dashboard/support/{ticket_user_id}/messages/{message_id}/attachment`
- Payment details in admin surfaces now show:
  - full list price
  - amount reserved from balance
  - amount applied from balance
  - remaining real-money payment

## Data model changes

- `users`
  - `balance_rub`
  - `balance_reserved_rub`
  - `referral_balance_migrated_at`
- new table:
  - `user_balance_events`
- `payment_records`
  - `list_price_amount`
  - `balance_reserved_amount`
  - `balance_applied_amount`
- `support_ticket_messages`
  - `attachment_file_id`
  - `attachment_file_unique_id`
  - `attachment_kind`
  - `attachment_name`
  - `attachment_mime_type`
  - `attachment_size`

## Validation

### Tests

- `./venv/bin/python -m unittest -q tests.test_bot_copy_updates tests.test_support_storage tests.test_dashboard_support_attachment tests.test_referral_balance tests.test_payment_finalization tests.test_dashboard_api_v2_support_contract`
- `./venv/bin/python -m unittest -q tests.test_confirm_external_payment_record tests.test_dashboard_vpn_repair tests.test_dashboard_api_v2_contract`

### Static checks

- `python3 -m compileall bot support_bot dashboard backend tests documentation`
- `git diff --check`

## Files of note

- `bot/db.py`
- `bot/payment_flow.py`
- `bot/manual_payments.py`
- `bot/handlers/tariffs.py`
- `bot/handlers/referrals.py`
- `bot/keyboards/devices.py`
- `bot/utils/texts.py`
- `support_bot/router.py`
- `support_bot/storage.py`
- `dashboard/main.py`
- `dashboard/services.py`
- `dashboard/templates/dashboard.html`
- `dashboard_v2/src/app/(dashboard)/payments/page.tsx`
- `dashboard_v2/src/app/(dashboard)/support/page.tsx`
- `dashboard_v2/src/lib/types.ts`
- `backend/core/models.py`
- `backend/core/schema.py`
- `dashboard/models.py`

## Follow-up note

The task intentionally keeps internal callback names and legacy identifiers stable where possible, so the user-facing copy improves without forcing a risky rename wave through the bot handlers.
