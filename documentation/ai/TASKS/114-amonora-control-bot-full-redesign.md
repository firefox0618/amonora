# 114 — Amonora Control Bot Full Redesign

## Context

`@amonora_control_bot` already existed as a dedicated internal bot for operational notifications, payment review and dashboard auth codes.

However, the current shell was still closer to a minimal alert console than to the full control interface described in `Дизайн бота контроль.txt`.

The redesign had to use only real Amonora aggregates and real Telegram/DB capabilities, without fake uptime/open-rate/read-time metrics.

## Scope

- redesign all current `control_bot` screens around the new shell:
  - `status`
  - `nodes`
  - `payments`
  - `users`
  - `alerts`
  - `login_codes`
  - `events`
  - `help`
- add `settings` and owner-only `broadcast` sections;
- add per-admin notification preferences in DB and apply them in dispatcher delivery;
- add campaign/template/trigger storage;
- extend `ops/access_reminders.py` into a DB-driven scheduled-campaign + trigger worker;
- add `users.last_activity_at` and touch points in the main bot + support ingress;
- keep all metrics honest and based only on real data.

## Constraints

- do not introduce fake operational metrics;
- keep `@amonora_control_bot` internal-only;
- send user campaigns/triggers via `@amonora_bot`, not via control bot;
- preserve existing payment review and auth-code flows;
- keep support ticket/media flows in `support_bot`.

## Acceptance criteria

- redesigned `control_bot` screens are available through commands and callbacks;
- `/events`, `/settings`, `/broadcast` exist;
- owner-only broadcast/triggers flow works from the control bot;
- dispatcher respects per-admin notification preferences;
- scheduled campaigns and automatic triggers are processed by the shared worker every 5 minutes;
- `users.last_activity_at` is updated from real bot/support actions;
- docs and task bookkeeping are updated.

## Validation

- control bot unit tests;
- access-reminder / trigger tests;
- dashboard auth/session and support regression smoke;
- `compileall`;
- `git diff --check`.
