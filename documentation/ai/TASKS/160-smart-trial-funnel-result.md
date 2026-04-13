# TASK 160 RESULT — Smart trial funnel on existing bot/backend contour

## Outcome
Implemented the smart trial funnel inside the existing Amonora control-plane instead of adding `n8n` or a second onboarding path.

## What changed
- `users` now persist:
  - `trial_activity_level`
  - `trial_engaged_at`
- `activate_trial()` resets new trials to `low` with empty engagement timestamp.
- New helper `mark_trial_technical_engagement()` upgrades a live trial from `low` to `active` on the first technical step and keeps the segment sticky for the rest of the same trial.
- Technical engagement is now marked from:
  - successful device creation
  - successful key/config delivery
  - successful QR delivery
  - successful routing-pack delivery
- Trigger engine now supports:
  - `trial_hours_since_start`
  - `trial_hours_before_expiry`
- Built-in smart trial rules were added:
  - `trial_active_2h`
  - `trial_low_2h`
  - `trial_active_24h`
  - `trial_low_24h`
  - `trial_final_6h`
- Legacy default rules `trial_ends_1d` and `trial_ends_today` are disabled in the built-in rollout set to avoid duplicate trial reminder chains.
- Campaign CTA now supports `open_devices`, which opens the `📱 Устройства` screen in `@amonora_bot`.

## Validation
- `./venv/bin/python -m py_compile backend/core/models.py backend/core/schema.py bot/utils/access.py bot/db.py bot/handlers/devices.py bot/handlers/start.py ops/access_reminders.py control_bot/storage.py control_bot/router.py tests/test_trial_funnel.py tests/test_access_reminders_triggers.py tests/test_bot_start_trial.py tests/test_control_trigger_defaults.py`
- `./venv/bin/python -m unittest tests.test_trial_funnel tests.test_access_reminders_triggers tests.test_bot_start_trial tests.test_control_trigger_defaults`

## Notes
- The funnel stays inside the current `bot + PostgreSQL + access_reminders + control triggers` architecture.
- Deduplication continues to rely on `ControlTriggerDeliveryLog`, not per-user sent flags.
- Channel pause/resume behavior from tasks `154` and `155` stays unchanged and now gates the smart trial funnel too.
