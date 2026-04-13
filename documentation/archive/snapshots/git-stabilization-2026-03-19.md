# Git Stabilization Plan — 2026-03-19

> Historical dated git/process snapshot. Useful for understanding the stabilization context on 2026-03-19, but not the primary source of current workflow rules if newer canonical docs disagree.

## Зачем это нужно

Текущее состояние репозитория рискованное:

- дерево грязное;
- часть рабочего состояния уже живёт в проде, но не зафиксирована в git;
- продовый `/opt/amonora_bot` развёрнут без `.git`, поэтому обычный `git status` на сервере не помогает понять parity;
- есть уже `8` локальных коммитов поверх `origin/develop`, плюс большой слой незакоммиченных изменений.

Главная цель этого файла:

- зафиксировать инвентаризацию;
- отделить `уже живёт в проде` от `локально / ещё не выкатано`;
- предложить безопасную commit-структуру;
- не допустить случайного `git add .` и потери prod-патчей.

## Снимок состояния на момент инвентаризации

### Локальный git

- ветка: `develop`
- относительно `origin/develop`: `ahead 8`
- staged changes: `0`
- tracked modified: `45`
- untracked: `13`

### Локальные коммиты, которых нет в origin

1. `68c1029` `Доработать основной Dashboard и вынести Knowledge Hub`
2. `8702b63` `Переключить основной доменный маршрут на Dashboard v2`
3. `3fa0d40` `Оптимизировать нагрузку Dashboard v2`
4. `56c8abc` `Усилить auth и профиль Dashboard v2`
5. `e0eb7ea` `Выкатить Dashboard v2 и усилить его продовый контур`
6. `229d1ba` `Добавить локальный Dashboard v2 на Next.js`
7. `fa232e1` `Реализовать финансовый контур и связность дашборда`
8. `41bd286` `Обновить README как витрину проекта Amonora`

### Важный operational fact

Продовый путь `/opt/amonora_bot` не является git-репозиторием.

Это означает:

- parity с продом нельзя определять через `git status` на сервере;
- ручные продовые патчи легко расходятся с локальной историей;
- перед push важно сравнивать не только с `origin`, но и с живым сервером.

## Сверка с продом

Для всех изменённых и untracked файлов была сделана batch-сверка с `/opt/amonora_bot` на `46.21.81.186`.

Результат:

- `42` файла локально совпадают с продом byte-to-byte
- `10` файлов локально отличаются от прода
- `7` файлов есть локально, но отсутствуют на проде

Практический вывод:

- большая часть грязного дерева уже фактически является live-state и не должна быть потеряна;
- нельзя просто “почистить” локальные изменения, потому что это местами сотрёт то, что уже работает в проде;
- сначала нужно закоммитить prod-parity блоки, а отдельно разобрать divergence-блок.

## Блок A. Локально совпадает с продом

Это самый безопасный кандидат на фиксацию в git: код уже живёт на сервере в таком же виде.

### A1. Dashboard backend и данные

- `dashboard/main.py`
- `dashboard/services.py`
- `dashboard/templates/dashboard.html`
- `dashboard/v2_data.py`

### A2. Dashboard v2 frontend и auth

- `dashboard_v2/next.config.ts`
- `dashboard_v2/public/favicon.svg`
- `dashboard_v2/src/app/(dashboard)/knowledge/page.tsx`
- `dashboard_v2/src/app/(dashboard)/overview/page.tsx`
- `dashboard_v2/src/app/(dashboard)/payments/page.tsx`
- `dashboard_v2/src/app/(dashboard)/servers/page.tsx`
- `dashboard_v2/src/app/(dashboard)/settings/page.tsx`
- `dashboard_v2/src/app/(dashboard)/support/page.tsx`
- `dashboard_v2/src/app/(dashboard)/traffic/page.tsx`
- `dashboard_v2/src/app/(dashboard)/users/page.tsx`
- `dashboard_v2/src/app/api/proxy/[...path]/route.ts`
- `dashboard_v2/src/app/auth/request-code/route.ts`
- `dashboard_v2/src/app/auth/verify/route.ts`
- `dashboard_v2/src/app/globals.css`
- `dashboard_v2/src/app/layout.tsx`
- `dashboard_v2/src/app/login/page.tsx`
- `dashboard_v2/src/app/verify/page.tsx`
- `dashboard_v2/src/components/app-shell.tsx`
- `dashboard_v2/src/components/providers.tsx`
- `dashboard_v2/src/components/toast-center.tsx`
- `dashboard_v2/src/components/ui.tsx`
- `dashboard_v2/src/lib/types.ts`

### A3. Bot / протоколы / устройства / runtime

- `bot/db.py`
- `bot/handlers/devices.py`
- `bot/handlers/protocol.py`
- `bot/keyboards/devices.py`
- `bot/keyboards/main_menu.py`
- `bot/keyboards/protocols.py`
- `bot/payment_flow.py`
- `bot/utils/regions.py`
- `bot/utils/vless.py`
- `bot/vpn_api.py`

### A4. Site / support / ops

- `landing/main.py`
- `landing/templates/index.html`
- `support_bot/router.py`
- `ops/server_watchdog.py`
- `ops/systemd/amonora-server-watchdog.timer`

### A5. Docs, уже совпадающие с продом

- `documentation/supporting/user-guide.md`

## Блок B. Локально отличается от прода

Это самые опасные файлы для следующего шага. Их нельзя слепо коммитить или слепо откатывать.

### B1. Bot / CTA / тексты / payment UX

- `bot/handlers/tariffs.py`
- `bot/manual_payments.py`
- `bot/utils/texts.py`

Комментарий:

- здесь высок шанс, что лежат локальные правки вокруг `Купить/Продлить`, payment copy и reminder-текстов;
- часть этих правок уже обсуждалась как важная для продукта, но parity с продом сейчас не полная;
- этот блок нужно сравнить с живым поведением бота перед коммитом.

### B2. Dashboard polling / docs meta

- `dashboard_v2/src/hooks/use-dashboard.ts`
- `documentation/README.md`
- `documentation/supporting/dashboard.md`
- `documentation/manifest.json`

Комментарий:

- это не самый опасный runtime-блок, но он влияет на knowledge routing и видимость docs внутри dashboard;
- особенно важно из-за перехода репозитория в `private`.

### B3. Ops / watchdog / support storage

- `ops/nginx/amonora-dashboard.server.conf`
- `ops/systemd/amonora-server-watchdog.service`
- `support_bot/storage.py`

Комментарий:

- здесь уже infra-level последствия;
- перед фиксацией нужен отдельный sanity-check, потому что это либо продовые drift-правки, либо локальные незавершённые изменения.

## Блок C. Локально есть, на проде отсутствует

Это новые файлы. Их нужно рассматривать как `ещё не выкатано` или `не доказано, что выкатано`.

### C1. Access reminders

- `ops/access_reminders.py`
- `ops/systemd/amonora-access-reminders.service`
- `ops/systemd/amonora-access-reminders.timer`
- `tests/test_access_reminders.py`

Комментарий:

- это цельный новый feature-блок;
- его удобно коммитить отдельно;
- это хороший кандидат на отдельный rollout после git-стабилизации.

### C2. Новая документация / аудит

- `documentation/supporting/dashboard-v2-deep-dive.md`
- `documentation/archive/snapshots/status-and-next-steps-2026-03-19.md`
- `documentation/archive/snapshots/system-audit-2026-03-19.md`

Комментарий:

- это безопасный блок для отдельного docs-коммита;
- в runtime не вмешивается.

## Предварительная оценка по доверию

### Высокое доверие

Это то, что уже совпадает с продом и должно быть сохранено в истории в первую очередь:

- весь блок `A`

### Среднее доверие

Это похоже на нужные изменения, но требует выборочной верификации перед фиксацией:

- `bot/handlers/tariffs.py`
- `bot/manual_payments.py`
- `bot/utils/texts.py`
- `dashboard_v2/src/hooks/use-dashboard.ts`
- `ops/nginx/amonora-dashboard.server.conf`
- `ops/systemd/amonora-server-watchdog.service`
- `support_bot/storage.py`

### Низкий риск, но не прод-parity

Это безопасные по смыслу, но не выкачанные в прод блоки:

- `documentation/supporting/dashboard-v2-deep-dive.md`
- `documentation/archive/snapshots/status-and-next-steps-2026-03-19.md`
- `documentation/archive/snapshots/system-audit-2026-03-19.md`
- `ops/access_reminders.py`
- `ops/systemd/amonora-access-reminders.service`
- `ops/systemd/amonora-access-reminders.timer`
- `tests/test_access_reminders.py`

## Рекомендуемая commit-структура

Важно:

- не делать один большой commit;
- не смешивать `prod-parity` и `not-on-prod-yet` в одном коммите;
- не трогать divergence-блок до отдельного разбора.

### Commit 1. Dashboard backend v2

Содержимое:

- `dashboard/main.py`
- `dashboard/services.py`
- `dashboard/templates/dashboard.html`
- `dashboard/v2_data.py`

Смысл:

- зафиксировать серверную часть нового dashboard и его data-layer.

### Commit 2. Dashboard v2 frontend core

Содержимое:

- `dashboard_v2/next.config.ts`
- `dashboard_v2/public/favicon.svg`
- `dashboard_v2/src/app/auth/request-code/route.ts`
- `dashboard_v2/src/app/auth/verify/route.ts`
- `dashboard_v2/src/app/layout.tsx`
- `dashboard_v2/src/app/login/page.tsx`
- `dashboard_v2/src/app/verify/page.tsx`
- `dashboard_v2/src/app/api/proxy/[...path]/route.ts`
- `dashboard_v2/src/app/globals.css`
- `dashboard_v2/src/components/app-shell.tsx`
- `dashboard_v2/src/components/providers.tsx`
- `dashboard_v2/src/components/toast-center.tsx`
- `dashboard_v2/src/components/ui.tsx`
- `dashboard_v2/src/lib/types.ts`

Смысл:

- auth, shell, proxy, favicon, styling и базовый runtime нового frontend-контура.

### Commit 3. Dashboard v2 pages

Содержимое:

- `dashboard_v2/src/app/(dashboard)/overview/page.tsx`
- `dashboard_v2/src/app/(dashboard)/users/page.tsx`
- `dashboard_v2/src/app/(dashboard)/servers/page.tsx`
- `dashboard_v2/src/app/(dashboard)/traffic/page.tsx`
- `dashboard_v2/src/app/(dashboard)/payments/page.tsx`
- `dashboard_v2/src/app/(dashboard)/support/page.tsx`
- `dashboard_v2/src/app/(dashboard)/settings/page.tsx`
- `dashboard_v2/src/app/(dashboard)/knowledge/page.tsx`

Смысл:

- страницы и UX нового dashboard без смешивания с bot/ops.

### Commit 4. Bot runtime: devices / protocols / regions

Содержимое:

- `bot/db.py`
- `bot/handlers/devices.py`
- `bot/handlers/protocol.py`
- `bot/keyboards/devices.py`
- `bot/keyboards/main_menu.py`
- `bot/keyboards/protocols.py`
- `bot/payment_flow.py`
- `bot/utils/regions.py`
- `bot/utils/vless.py`
- `bot/vpn_api.py`

Смысл:

- зафиксировать уже живой bot-side runtime и device/protocol flow.

### Commit 5. Landing + support router + watchdog

Содержимое:

- `landing/main.py`
- `landing/templates/index.html`
- `support_bot/router.py`
- `ops/server_watchdog.py`
- `ops/systemd/amonora-server-watchdog.timer`
- `documentation/supporting/user-guide.md`

Смысл:

- собрать отдельно все уже-живые изменения вне dashboard core.

### Commit 6. Docs and audit pack

Содержимое:

- `documentation/supporting/dashboard-v2-deep-dive.md`
- `documentation/archive/snapshots/status-and-next-steps-2026-03-19.md`
- `documentation/archive/snapshots/system-audit-2026-03-19.md`

Смысл:

- безопасно зафиксировать документацию, не влияя на runtime.

### Commit 7. Access reminders

Содержимое:

- `ops/access_reminders.py`
- `ops/systemd/amonora-access-reminders.service`
- `ops/systemd/amonora-access-reminders.timer`
- `tests/test_access_reminders.py`

Смысл:

- выделить напоминания в отдельный feature commit и потом отдельно выкатить.

## Что нельзя делать прямо сейчас

Нельзя:

- `git add .`
- `git commit -am "..."`
- `git reset --hard`
- `git checkout -- .`
- пытаться “просто push-нуть 8 локальных коммитов”, не разобрав divergence-блок

Почему:

- часть live-state лежит только в dirty tree;
- часть файлов уже совпадает с продом, но ещё не в истории;
- часть файлов расходится с продом и требует решения.

## Самый безопасный следующий шаг

1. Зафиксировать в git сначала `prod-parity` блоки `A1-A5` по отдельным commit-пакетам.
2. Отдельно разобрать блок `B` и только после этого решать, что реально идёт в push.
3. Потом добавить `C1-C2` как новые, чисто отделённые коммиты.
4. Лишь после этого делать push в origin.

## Короткий итог

Сейчас грязное дерево уже нельзя считать просто “локальной недоделкой”.

По факту оно распадается на три разные сущности:

- уже живой prod-state, который надо срочно сохранить в истории;
- divergence-файлы, которые нельзя трогать без отдельного решения;
- новые локальные feature/doc-блоки, которые удобно коммитить отдельно.

То есть правильная стратегия сейчас не `чистить дерево`, а `аккуратно забрать в git то, что уже стало реальностью`.
