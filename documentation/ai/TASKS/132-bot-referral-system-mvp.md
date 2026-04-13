# TASK 132 — Bot Referral System MVP

## Status
Completed

## Goal
Вернуть реферальную систему в основной бот как живой продуктовый сценарий, а не как placeholder.

## Why
Текущий referral seam уже существовал в backend/payment-контуре, но пользовательский экран был отключён, бонус был жёстко зафиксирован на `50 ₽`, а привязка жила на хрупком формате `ref_<telegram_id>`.

## Context
Relevant docs and code areas:
- `documentation/FEATURES.md`
- `documentation/PUBLIC_SURFACES.md`
- `documentation/ai/STATE.md`
- `backend/core/models.py`
- `backend/core/schema.py`
- `bot/db.py`
- `bot/payment_flow.py`
- `bot/handlers/start.py`
- `bot/handlers/referrals.py`
- `bot/keyboards/referrals.py`
- `bot/utils/referrals.py`
- `bot/utils/texts.py`
- `tests/test_referral_ui.py`
- `tests/test_referral_balance.py`
- `tests/test_referral_utils.py`

## Current behavior
До этой задачи основной бот показывал `пока в разработке`, а backend side still only knew a legacy one-shot referral bonus.

## Desired behavior
После задачи бот должен:
- поддерживать персональные `ref_code` ссылки;
- фиксировать связь пригласивший -> приглашённый;
- начислять бонусы обоим после первой подтверждённой оплаты приглашённого;
- показывать пользователю живой referral dashboard со статистикой и progress-геймификацией.

## Scope
Included:
- `users.ref_code` and `users.referral_earned_total_rub`
- tables `referrals` and `referral_rewards`
- start-token binding with legacy compatibility
- tariff-based referral rewards on confirmed payments
- live referral screen in `@amonora_bot`
- user notifications on referral registration / first paid reward
- tests and docs updates

## Out of scope
Not included:
- leaderboard
- отдельный dashboard referral analytics UI
- сложный anti-fraud beyond basic self/duplicate/first-payment guards
- manual admin referral adjustments

## Constraints
Important limitations:
- keep existing payment and balance flows intact
- keep `Telegram Stars`, `Platega`, manual rollback paths working
- do not split balance into a second separate currency ledger
- keep legacy `ref_<telegram_id>` invite links as fallback compatibility

## Risks
Potential regressions or sensitive areas:
- duplicate reward issuance on repeated payment sync
- mismatch between legacy referral migration and new reward rows
- copy/tests drift because placeholder-related assertions were previously canonical

## Acceptance criteria
Concrete conditions for completion:
- `/start ref_<code>` binds the inviter once and blocks self-referrals
- referral screen shows link, balance, earned total, invited/paid stats, level, and progress
- first confirmed qualifying tariff payment grants the configured bonus to both users exactly once
- repeated sync / repeated successful-payment handling does not duplicate reward
- targeted tests pass

## Validation
Tests and manual checks required:
- `./venv/bin/python -m py_compile backend/core/models.py backend/core/schema.py bot/utils/referrals.py bot/keyboards/referrals.py bot/db.py bot/utils/texts.py bot/handlers/referrals.py bot/handlers/start.py bot/payment_flow.py bot/platega_flow.py bot/manual_payments.py bot/handlers/tariffs.py`
- `./venv/bin/python -m unittest -q tests.test_referral_ui tests.test_referral_balance tests.test_referral_utils tests.test_bot_payment_handlers tests.test_bot_copy_updates`

## Deliverables
- code changes
- docs updates
- short implementation summary
