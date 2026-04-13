# TASK 135 — Referral Notifications Integration

## Status
Completed

## Goal
Довести уведомления реферальной системы до явного и централизованного `payment_success`-flow.

## Context
Relevant areas:
- `bot/payment_flow.py`
- `bot/db.py`
- `bot/user_notifications.py`
- `bot/keyboards/referrals.py`
- `bot/utils/texts.py`
- `landing/main.py`
- `bot/manual_payments.py`
- `bot/handlers/tariffs.py`
- `tests/test_referral_notifications.py`
- `tests/test_referral_ui.py`

## Desired behavior
- бонус начисляется только после первой подтверждённой оплаты приглашённого;
- одно начисление даёт один комплект уведомлений без повторов;
- реферал получает сообщение `Вам начислены бонусные рубли`;
- реферер получает сообщение `Ваш друг оплатил, вам начислено X бонусных рублей`;
- доставка идёт через bot/in-app flow и может дополнительно уходить в push webhook, если он подключён;
- начисление и доставка логируются в control event log;
- текст приглашения для share-flow обновлён и вынесен в env-configurable copy.

## Validation
- `./venv/bin/python -m unittest -q tests.test_referral_notifications tests.test_referral_ui tests.test_referral_balance tests.test_bot_copy_updates tests.test_bot_payment_handlers`
