# 111 — Referral Balance Backfill, Panel UI Unification, and WireGuard Cleanup

## Context

После перехода на денежную реферальную систему и нового UI Панели управления в репозитории и runtime оставались хвосты:

- старая кнопка `Рефералы`;
- исторические пользователи с приглашёнными друзьями, но без рублей на Балансе;
- второй top-level frontend-контур `dashboard_v2`;
- user-facing и runtime-следы `WireGuard`;
- support media policy без жёсткого ограничения на допустимые media types.

## Scope

- переименовать пользовательскую кнопку в `Реферальная система`;
- добавить safe backfill / reconcile для старых реферальных начислений;
- ограничить user-side media в support bot до `text + photo + video + audio`;
- перенести новый admin frontend из `dashboard_v2` в `dashboard/ui`;
- переименовать operator-facing контур в `Панель управления`;
- убрать живые кодовые и документированные следы `WireGuard`;
- обновить пользовательскую и операторскую документацию.

## Constraints

- не ломать активных пользователей и текущие payment/access flows;
- не ломать `dashboard` backend, который остаётся source-of-truth для admin API;
- не трогать `.env` и секреты в репозитории;
- на проде обязательно сделать pre-change backup и проверить новый UI build.

## Acceptance criteria

- в основном боте видна кнопка `🎁 Реферальная система`;
- старые рефералы могут быть доначислены в рублях через reconcile/backfill;
- `548589949` получает `50 ₽` за одного legacy приглашённого друга;
- support bot отклоняет video notes / documents / stickers / animation / voice и принимает только `text`, `photo`, `video`, `audio`;
- в репозитории больше нет top-level папки `dashboard_v2`;
- новый UI живёт в `dashboard/ui`, а production service использует `amonora-dashboard-ui.service`;
- в живом коде и актуальной документации нет следов `WireGuard`;
- legacy `wireguard` inbound на Estonia удалён из `3x-ui`.

## Validation

- unit/regression tests для referral/backfill, bot copy, support media, payments, dashboard support;
- `python3 -m compileall bot support_bot dashboard control_bot ops documentation tests`;
- `git diff --check`;
- production build `dashboard/ui`;
- production smoke:
  - services active;
  - `dashboard/ui` отвечает на `/login`;
  - referral reconcile завершён;
  - Estonia inbound list больше не содержит `wireguard`.
