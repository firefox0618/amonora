# TASK 114 — Amonora Control Bot Full Redesign Result

## Result

`@amonora_control_bot` was fully redesigned around the shell from `Дизайн бота контроль.txt`, while staying grounded in real Amonora data and real Telegram/runtime limits.

The control bot is now both:

- an operational notification console;
- an owner-facing control surface for notification preferences, campaigns, templates and automatic triggers.

## What changed

### Control bot shell

- redesigned `/start`, `/status`, `/nodes`, `/payments`, `/users`, `/alerts`, `/login_codes`, `/events`, `/help`;
- added `/settings`;
- added owner-only `/broadcast`;
- updated live event formatting to compact operational-style notifications.

### Preferences and roles

- introduced per-admin notification preferences;
- made delivery respect:
  - global env category flags;
  - per-admin DB preferences;
  - night-mode critical-only policy;
- kept role-aware access for owner/admin/operator/support-view-only.

### Broadcasts and triggers

- added DB-backed templates, campaigns, deliveries and trigger rules;
- added owner flows for:
  - admin pushes;
  - manual user broadcasts;
  - template save/use/edit/delete;
  - trigger view/toggle/edit/test;
- added CTA delivery model with supported preset actions only.

### Shared worker

- extended `amonora-access-reminders` into a shared 5-minute worker for:
  - scheduled campaigns;
  - DB-driven trigger rules;
  - inactivity/access/trial follow-ups.

### Activity seam

- added `users.last_activity_at`;
- update points now exist in:
  - main bot message/callback middleware;
  - trial/subscription activation paths;
  - support ingress.

## Files changed

- `backend/core/models.py`
- `backend/core/schema.py`
- `bot/db.py`
- `bot/handlers/start.py`
- `bot/main.py`
- `bot/middlewares/activity.py`
- `control_bot/dispatcher.py`
- `control_bot/keyboards.py`
- `control_bot/main.py`
- `control_bot/messaging.py`
- `control_bot/queries.py`
- `control_bot/router.py`
- `control_bot/storage.py`
- `ops/access_reminders.py`
- `ops/systemd/amonora-access-reminders.timer`
- `support_bot/router.py`
- `documentation/ARCHITECTURE.md`
- `documentation/DOMAIN.md`
- `documentation/FEATURES.md`
- `documentation/RUNBOOK.md`
- `documentation/supporting/amonora-control-bot.md`
- `documentation/ai/STATE.md`

## Validation

- `./venv/bin/python -m unittest -q tests.test_control_router tests.test_control_queries tests.test_control_dispatcher tests.test_access_reminders_triggers`
- `./venv/bin/python -m unittest -q tests.test_dashboard_api_v2_contract tests.test_dashboard_support_attachment`
- `./venv/bin/python -m unittest -q tests.test_dashboard_auth_session tests.test_support_storage tests.test_support_router_policy`
- `./venv/bin/python -m unittest -q tests.test_bot_copy_updates tests.test_referral_ui tests.test_bot_devices_ui`
- `PYTHONPATH=. ./venv/bin/python tests/test_access_reminders.py`
- `python3 -m compileall control_bot bot support_bot backend ops tests documentation`
- `git diff --check`

## Notes

- metrics like open-rate/read-time were intentionally not added because the current Telegram/runtime stack does not provide them honestly;
- user-facing campaign CTA callbacks are handled in `@amonora_bot`, not in the control bot itself;
- the shared worker still keeps its historical service name `amonora-access-reminders`, but its real role is now broader than legacy access reminders.
