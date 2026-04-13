# DASHBOARD COVERAGE AUDIT

## Назначение

Этот документ фиксирует покрытие legacy UI из `dashboard` новым UI в `dashboard/ui`.

Цель документа:

- не путать наличие похожего route с реальным feature coverage;
- понять, что уже реально покрыто в `dashboard/ui`;
- понять, что остаётся только в legacy UI;
- понять, какие зоны ещё нельзя трогать.

## Правило чтения

Здесь оценивается именно UI coverage.

Это не то же самое, что backend ownership:

- backend/API/auth/service layer остаётся в `dashboard`;
- `dashboard/ui` оценивается только как новый интерфейсный слой.

Статусы:

- `legacy only`
- `v2 only`
- `both`
- `partial`
- `unknown`

## Coverage matrix

| Flow | Legacy UI (`dashboard`) | New UI (`dashboard/ui`) | Status | Comment |
| --- | --- | --- | --- | --- |
| Dashboard / home / overview | Есть `/dashboard/overview` и overview widgets | Есть `/overview` с KPI, alerts, charts, payments rail | `both` | Новый overview выглядит основным, но legacy overview ещё существует |
| Users | Есть `/dashboard/users`, `/dashboard/users/{id}`, trial/extend/block/protocol/devices/delete | Есть `/users` с list + detail + device actions + extend/block/delete | `both` | Это одна из самых полно покрытых зон |
| Payments | Есть `/dashboard/payments` с confirm/reject/create | Есть `/payments` с records, confirm/reject/delete/create | `both` | Базовый payments flow покрыт по обеим сторонам |
| Finance | Есть отдельный `/dashboard/finance` | Finance встроен в `/payments` page | `partial` | Функциональность есть в v2, но route/model split уже другой |
| Nodes / servers | Есть `/dashboard/servers`, snapshots, create/status | Есть `/servers` и отдельный `/traffic` | `both` | Новый UI покрывает server-side work, но логика legacy split была другой |
| Access / VPN | Есть отдельный `/dashboard/vpn` с device/country/protocol/access perspective | Нет отдельной page `access`; access действия размазаны между `/users`, `/servers`, `/traffic` | `partial` | Самая опасная зона: concept-level coverage есть, dedicated UI parity нет |
| Support | Есть `/dashboard/support`, detail, assign/transfer/reply/close | Есть `/support` с queue + detail + assign/transfer/reply/close | `both` | Сильное покрытие в v2 |
| Settings / services / env / tariffs | Есть `/dashboard/services`, actions, tariffs, env | Есть `/settings` с services/env/tariffs и related admin controls | `both` | Основной settings flow уже перенесён в v2 |
| Docs / knowledge | Есть `/dashboard/docs` | Есть `/knowledge` | `both` | Покрытие есть, но naming changed |
| Alerts | В legacy есть alert-like widgets на overview | В v2 есть alerts rail на overview, но нет отдельной alerts page | `partial` | Alert awareness есть, полноценного alerts module ещё нет |
| Traffic analytics | В legacy нет отдельной новой traffic page, есть server/vpn views | Есть `/traffic` | `v2 only` | Это уже новый отдельный UI-срез |
| Login / verify frontend | Есть `login.html` / `verify.html` | Есть `/login` / `/verify` pages | `both` | Frontend дублируется, backend verification остаётся в `dashboard` |

## Что реально остаётся legacy-only или близко к этому

На текущем этапе ближе всего к legacy-only:

- Jinja rendering layer;
- dedicated `/dashboard/vpn` page as a separate access-first screen;
- old route structure `/dashboard/*` как основной интерфейс;
- старый visual shell и template-driven page composition.

Важно:

это не значит, что underlying feature logic стала legacy.

## High-risk legacy-oriented areas

Самые чувствительные зоны, где легко ошибочно решить “уже всё перенесли”:

### 1. Access / VPN

Почему риск высокий:

- в legacy это отдельный смысловой раздел;
- в v2 нет отдельной `access` page;
- часть access-операций покрыта через users/detail/devices и servers/traffic, но не как единый операторский экран.

### 2. Finance route equivalence

Почему риск средний:

- в legacy был отдельный `/dashboard/finance`;
- в v2 finance встроен в `/payments`;
- route parity не равна information parity.

### 3. Alerts

Почему риск средний:

- сигналы и attention rail есть;
- отдельного полноценного alerts page нет;
- implementation map панели предполагает выделенный alerts section позже.

## Что пока нельзя удалять

Нельзя удалять на основании текущего coverage audit:

- `dashboard/templates/dashboard.html`
- `dashboard/templates/login.html`
- `dashboard/templates/verify.html`
- legacy routes `/dashboard/*`
- dedicated `/dashboard/vpn` flow
- anything tied to auth/session/backend ownership in `dashboard`

Причина:

наличие похожих экранов в v2 ещё не доказывает полную migration equivalence.

## Что уже выглядит покрытым достаточно уверенно

С высокой уверенностью в v2 уже покрыты:

- overview/home;
- users + user detail;
- payments base flow;
- support queue + support detail;
- settings/services/env/tariffs;
- docs/knowledge;
- servers and traffic-facing monitoring surfaces.

Это не означает, что legacy можно удалить, но означает, что v2 уже является основным UI для этих зон.

## Что можно мигрировать следующим

### Safe next migrations

- formal parity audit for `access/vpn` as a dedicated admin flow;
- formal parity audit for alerts as a dedicated section;
- route-by-route mapping of legacy pages to v2 pages;
- documenting edge-case actions that still exist only in legacy templates;
- backlog decomposition from `DASHBOARD_IMPLEMENTATION_MAP.md` focused on access and alerts.

### Most likely next UI candidates

- dedicated Access page in v2;
- dedicated Alerts page in v2;
- explicit finance parity checklist;
- explicit legacy login/verify deprecation criteria after frontend/backend split is better documented.

## Do not remove yet

- legacy VPN page
- Jinja login/verify templates
- old dashboard route layer
- any admin action whose parity was inferred only from route naming

## Итог

Если упростить итог coverage audit:

- `dashboard/ui` уже покрывает большую часть основного operator UI;
- `dashboard` legacy UI всё ещё содержит transition-sensitive surfaces;
- strongest v2 coverage: users, payments, support, settings, overview;
- weakest / most incomplete parity: access/vpn and alerts;
- cleanup without a dedicated parity pass would still be risky.
