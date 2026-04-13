# DASHBOARD BOUNDARY MAP

## Назначение

Этот документ фиксирует текущую границу ответственности между `dashboard` и `dashboard/ui`.

Он нужен для того, чтобы:

- не считать `dashboard` полностью legacy;
- не считать `dashboard/ui` полностью завершённой заменой;
- безопасно планировать feature work и cleanup;
- не удалять живые части админского контура раньше времени.

## Короткий вывод

По текущему состоянию репозитория:

- `dashboard` остаётся обязательным backend/API и auth-контуром админки;
- `dashboard/ui` уже является основным новым UI для большинства рабочих admin-маршрутов;
- legacy Jinja UI в `dashboard` всё ещё существует и не должен удаляться вслепую;
- граница проходит не по принципу “старое vs новое”, а по принципу “backend/control plane vs frontend/admin UI”.

## Что сейчас живёт в `dashboard`

### 1. Backend/API админки

В `dashboard` живут обязательные backend-обязанности:

- FastAPI application;
- admin session model;
- auth logic;
- Telegram-code login flow;
- API `/dashboard/api/v2/*` для `dashboard/ui`;
- payload builders через `dashboard/v2_data.py`;
- service/domain helpers через `dashboard/services.py`.

Это не legacy-слой. Это активное ядро admin control plane.

### 2. Legacy Jinja UI

В `dashboard` всё ещё живут серверно-рендеренные страницы:

- `/login`
- `/verify`
- `/dashboard/overview`
- `/dashboard/users`
- `/dashboard/vpn`
- `/dashboard/support`
- `/dashboard/payments`
- `/dashboard/finance`
- `/dashboard/servers`
- `/dashboard/services`
- `/dashboard/docs`

Также там живут:

- `dashboard/templates/login.html`
- `dashboard/templates/verify.html`
- `dashboard/templates/dashboard.html`
- legacy static assets

Этот UI-слой уже не является главным направлением развития, но всё ещё существует в коде и частично участвует в совместимости.

### 3. Активная доменная и административная логика

В `dashboard` остаётся активная логика по:

- пользователям;
- trial / extend / block / protocol;
- устройствам;
- support ticket operations;
- платежам;
- finance entries;
- managed servers;
- services/env/tariffs;
- docs and operations reports;
- search / notifications / session state.

Следовательно, `dashboard` нельзя трактовать как “просто старый UI”.

## Что уже реально есть в `dashboard/ui`

`dashboard/ui` уже покрывает основной новый frontend admin-контура.

### Реально реализованные UI-поверхности

В коде есть страницы:

- `/login`
- `/verify`
- `/overview`
- `/users`
- `/servers`
- `/traffic`
- `/payments`
- `/support`
- `/knowledge`
- `/settings`

Также реализованы:

- app shell;
- sidebar/navigation;
- global search;
- notifications drawer;
- profile overlay;
- session-aware frontend flow;
- proxy layer `/api/proxy/*`.

### Реальная роль `dashboard/ui`

`dashboard/ui` отвечает за:

- новый UI;
- layout, forms, charts, page state;
- frontend polling and rendering;
- browser-side interaction flow.

Он не является самостоятельным источником истины и не содержит основной доменной логики.

## Что дублируется или находится в переходной зоне

### 1. Login / verify flow

Переходная зона:

- в `dashboard` есть legacy routes `/login` и `/verify`;
- в `dashboard/ui` тоже есть `/login` и `/verify`;
- при этом backend-проверка логина, отправка кода и верификация всё равно живут в `dashboard` API/backend.

Вывод:

frontend уже новый, но auth backend остаётся в `dashboard`.

### 2. Admin sections

Есть дублирование на уровне старых и новых экранов для:

- overview;
- users;
- support;
- payments;
- servers;
- services/settings;
- docs/knowledge.

Но это дублирование в основном UI-уровня, а не предметной логики.

### 3. Legacy routes через nginx

Через `nginx` legacy-маршруты переводятся в новый UI:

- `/dashboard/overview` -> `/overview`
- `/dashboard/users` -> `/users`
- `/dashboard/vpn` и `/dashboard/servers` -> `/servers`
- `/dashboard/payments` и `/dashboard/finance` -> `/payments`
- `/dashboard/support` -> `/support`
- `/dashboard/services` -> `/settings`
- `/dashboard/docs` -> `/knowledge`

Это явный признак переходной схемы, а не полного удаления старого слоя.

## Что считается legacy-only

На текущем этапе к legacy-only можно осторожно относить:

- Jinja templates в `dashboard/templates/`;
- старые server-rendered dashboard pages;
- старые `/dashboard/*` UI-маршруты как основной способ взаимодействия.

Но даже здесь важно различать:

- legacy UI;
- active backend.

Legacy-only сейчас не равен “всё внутри `dashboard`”.

## Что пока нельзя трогать

Нельзя трогать без отдельной миграционной проверки:

- `dashboard/main.py` как backend/API слой;
- `/dashboard/api/v2/*`;
- auth/session logic;
- service-layer в `dashboard/services.py`;
- payload builders в `dashboard/v2_data.py`;
- backend-side docs, settings, payments, support, server operations;
- legacy routes, пока не подтверждено, что на них больше никто не опирается.

Также нельзя удалять Jinja UI только потому, что у нового фронтенда есть похожие страницы.

## Что уже можно считать основным новым UI

На текущем этапе основным новым UI можно считать:

- login / verify frontend;
- overview;
- users;
- servers;
- traffic;
- payments;
- support;
- knowledge;
- settings.

То есть основной операторский визуальный слой уже действительно живёт в `dashboard/ui`.

## Что можно мигрировать следующим

Наиболее безопасные следующие направления миграции:

### 1. Явная карта coverage legacy UI vs v2

Нужно поэкранно зафиксировать:

- какой legacy page полностью покрыт в `dashboard/ui`;
- какой покрыт частично;
- какой ещё имеет скрытые backend/UI зависимости.

Это безопасный следующий шаг, потому что он не меняет runtime.

### 2. Сужение legacy Jinja как интерфейса

После coverage map можно постепенно:

- помечать legacy UI как deprecated;
- уменьшать зависимость команды от старых Jinja-экранов;
- оставлять `dashboard` как backend/API-first слой.

### 3. Выделение unresolved зон

Нужно отдельно проверить:

- есть ли в legacy UI экраны или действия, которых ещё нет в v2;
- есть ли в finance/services/docs скрытые функции, покрытые только старым шаблонным интерфейсом;
- насколько `traffic` page в v2 закрывает реальные admin needs по сравнению с legacy server/vpn views.

## Safe next migrations

- формальный coverage audit legacy pages vs v2 pages;
- документирование unresolved admin actions;
- перевод planning/backlog вокруг панели на `dashboard/ui` pages as primary UI;
- постепенная маркировка Jinja UI как deprecated, но не удалённого слоя.

## Do not touch yet

- удаление `dashboard/templates/*`;
- удаление `/dashboard/api/v2/*`;
- удаление auth/session backend;
- удаление service-operations из `dashboard/services.py`;
- assumption that `dashboard/ui` fully replaces `dashboard`.

## Итоговая граница

Если упростить до одной рабочей формулы:

```text
dashboard = active admin backend + API + auth/session + legacy UI
dashboard/ui = primary new admin frontend
```

А если ещё точнее:

```text
dashboard/ui renders the admin interface
dashboard still owns the admin control plane backend
```

Это и есть текущая реальная граница, от которой нужно отталкиваться в дальнейшей работе.
