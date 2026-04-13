# TASK 154 — Trial channel membership enforcement result

## Status
Completed

## What changed
- `users` now persist `trial_channel_unsubscribed_at`, which marks a trial as paused because the user left the required channel before trial expiry;
- access helpers no longer treat paused trial as active access, so user-facing and runtime access checks stop granting trial while channel membership is missing;
- `@amonora_bot` `/start` now explains paused trial correctly and resumes the same remaining trial after the user re-subscribes instead of issuing a new one;
- `ops/access_reminders.py` now enforces channel membership for active-trial users, revokes VPN access when they unsubscribe, and restores the same trial window when they return.

## Files changed
- `backend/core/models.py`
- `backend/core/schema.py`
- `bot/utils/access.py`
- `bot/db.py`
- `bot/handlers/start.py`
- `bot/utils/texts.py`
- `ops/access_reminders.py`
- `tests/test_trial_access_guard.py`
- `tests/test_access_logic.py`
- `tests/test_bot_start_trial.py`
- `tests/test_expired_access_revocation.py`
- `tests/test_access_reminders.py`
- `tests/test_bot_copy_updates.py`
- `documentation/FEATURES.md`
- `documentation/DOMAIN.md`
- `documentation/ai/STATE.md`

## Validation
- `./venv/bin/python -m unittest tests.test_trial_access_guard tests.test_bot_start_trial tests.test_expired_access_revocation`
- `PYTHONPATH=. ./venv/bin/python tests/test_access_reminders.py`
- `PYTHONPATH=. ./venv/bin/python tests/test_access_logic.py`
