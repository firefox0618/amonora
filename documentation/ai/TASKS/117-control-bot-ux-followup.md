# TASK 117 — Control Bot UX Follow-Up

## Context

After the full `@amonora_control_bot` redesign, the live admin flow still had several UX issues:

- `/start` was too noisy and wrapped separators on mobile;
- `Платежи` still biased toward panel-style links instead of Telegram-first review;
- `Авторизация` and `События` showed redundant actions and weak formatting;
- node labels and region-to-device counters were confusing, especially for Sweden/unknown regions;
- node/manual-payment notifications were still too long for fast operator work.

## Scope

Tighten the internal UX without changing the underlying payment, auth, trigger, or dispatcher architecture:

- simplify shell/buttons;
- shorten operational texts and notifications;
- remove duplicate/back buttons where the reply keyboard already covers navigation;
- keep payment review inside Telegram;
- fix region-count mapping so unknown regions do not fall back to Germany;
- normalize node names for Germany / Estonia / Denmark / Sweden.

## Constraints

- no new broad refactor;
- preserve current roles, commands, and payment review semantics;
- keep `/alerts` for compatibility, but it no longer needs to dominate the main shell;
- do not reintroduce panel deep-links into payment review.

## Acceptance criteria

- `/start` shows compact profile-only entry;
- `Статус системы`, `Ноды`, `Платежи`, `Пользователи`, `Авторизация`, `События`, `Настройки` use shorter operational formatting;
- `Платежи` open review records in Telegram instead of panel links;
- live manual payment notifications arrive with `Подтвердить / Отклонить`;
- node recovery notifications are short and include readable duration;
- Sweden and unknown region codes no longer collapse into Germany device counters.
