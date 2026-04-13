# Amonora Control Bot Redesign Report — 2026-03-22

## Scope

Полный redesign `@amonora_control_bot` по `Дизайн бота контроль.txt` с переходом от минимального alert-console к полноценному internal control surface.

## Что внедрено

### Новый shell

- `/start`
- `/status`
- `/nodes`
- `/payments`
- `/users`
- `/alerts`
- `/login_codes`
- `/events`
- `/settings`
- `/broadcast`
- `/help`

### Owner / admin control layer

- per-admin notification preferences;
- owner-only `Рассылка / Триггеры`;
- template storage;
- campaign/delivery storage;
- trigger-rule storage;
- active dashboard sessions summary and terminate-all for owner.

### Shared messaging worker

- `amonora-access-reminders.service/.timer` now acts as a 5-minute worker for:
  - scheduled campaigns;
  - DB-driven trigger rules;
  - inactivity/access/trial follow-up sends.

### Activity seam

- `users.last_activity_at` added as the current source of truth for inactivity logic;
- touched from main bot message/callback middleware;
- touched from support ingress;
- touched on trial/subscription activation.

## What stayed intentionally honest

- no fake `open rate`;
- no fake `read time`;
- no fake uptime percentages;
- only real `sent / failed / clicked / converted` counters where the stack can measure them.

## Validation

- `48` local tests passed across control bot, access reminders, dashboard auth/support seams, and bot regressions;
- `python3 -m compileall control_bot bot support_bot backend ops tests documentation` passed;
- `git diff --check` passed.

## Deployment note

Code is ready for production rollout, but direct SSH connectivity to the core host timed out during this pass from the current environment, so server-side restart must be completed once network access to the host is available again.
