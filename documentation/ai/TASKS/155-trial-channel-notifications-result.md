# TASK 155 — Trial channel pause/resume notifications result

## Status
Completed

## What changed
- trial channel pause/resume copy now has dedicated proactive notification text in `@amonora_bot`;
- `ops/access_reminders.py` now keeps a separate `trial_channel_membership_notice` dedupe state, so it can send a one-time explanation message even for users whose trial was already paused earlier;
- pause notifications now include direct buttons to rejoin the channel and reopen `@amonora_bot`;
- resume notifications confirm that the original remaining trial was restored instead of issuing a new trial.

## Files changed
- `bot/utils/texts.py`
- `ops/access_reminders.py`
- `tests/test_expired_access_revocation.py`
- `tests/test_bot_copy_updates.py`
- `documentation/FEATURES.md`
- `documentation/ai/STATE.md`

## Validation
- `./venv/bin/python -m unittest tests.test_expired_access_revocation tests.test_bot_copy_updates`
- `./venv/bin/python -m py_compile bot/utils/texts.py ops/access_reminders.py`
