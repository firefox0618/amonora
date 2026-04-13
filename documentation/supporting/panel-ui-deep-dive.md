# Панель управления UI: структура, функции и аудит

> Supporting deep-dive document. Use [ARCHITECTURE.md](/home/dextrmed/projects/amonora_bot/documentation/ARCHITECTURE.md), [RUNBOOK.md](/home/dextrmed/projects/amonora_bot/documentation/RUNBOOK.md) and [product/DASHBOARD_BOUNDARY_MAP.md](/home/dextrmed/projects/amonora_bot/documentation/product/DASHBOARD_BOUNDARY_MAP.md) as canonical current-state references first.

_Актуально по коду и infra на 2026-03-19._

## 1. Что это такое

`Панель управления UI` — frontend-контур админки Amonora на `Next.js`, который работает поверх существующего backend `FastAPI /dashboard/api/v2`.

Это не отдельная система со своей бизнес-логикой.  
Он:

- рендерит новый SaaS-интерфейс;
- использует текущую admin auth-схему;
- ходит в backend через proxy route;
- показывает пользователей, серверы, трафик, платежи, поддержку, настройки и базу знаний;
- в проде уже используется как основной новый интерфейс для маршрутов `overview/users/servers/traffic/payments/support/knowledge/settings`.

Важный нюанс:

- корень сайта `/` остаётся за landing-контуром;
- сам UI Панели управления висит не на всём домене целиком, а на конкретных маршрутах;
- старые `/dashboard/*` и `/v2/*` через `nginx` редиректятся в новый контур.

## 2. Prod-схема

### Внешняя схема

| Слой | Что делает | Куда смотрит |
| --- | --- | --- |
| `nginx` | принимает HTTPS-трафик | `amonoraconnect.com` |
| Панель управления UI | Next.js frontend | `127.0.0.1:3001` |
| Dashboard backend | FastAPI API и admin session model | `127.0.0.1:8088` |
| Landing / старый контур | сайт и остальная веб-часть | `127.0.0.1:8090` |

### Какие маршруты реально обслуживает v2

Новый frontend получает запросы на:

- `/login`
- `/verify`
- `/_next/*`
- `/api/proxy/*`
- `/overview`
- `/users`
- `/servers`
- `/traffic`
- `/payments`
- `/support`
- `/knowledge`
- `/settings`

Остальное по `location /` уходит в landing на `127.0.0.1:8090`.

### Legacy-маршруты

Через `nginx` оставлены редиректы:

- `/v2` -> `/overview`
- `/v2/*` -> `/*`
- `/dashboard/overview` -> `/overview`
- `/dashboard/users` -> `/users`
- `/dashboard/vpn` -> `/servers`
- `/dashboard/servers` -> `/servers`
- `/dashboard/payments` -> `/payments`
- `/dashboard/finance` -> `/payments`
- `/dashboard/support` -> `/support`
- `/dashboard/services` -> `/settings`
- `/dashboard/docs` -> `/knowledge`

Это полезно для обратной совместимости, но создаёт слой исторической сложности.

## 3. Техстек

### Frontend

- `Next.js 16.1.6`
- `React 19.2.3`
- `TypeScript`
- `Tailwind CSS 4`
- `TanStack Query 5`
- `Recharts`
- `lucide-react`

### Backend / data

- `FastAPI`
- `SQLAlchemy`
- текущие модели `User`, `VpnClient`, `PaymentRecord`, `ManagedServer`, `DashboardAdmin`, `DashboardSession`, `FinanceEntry`
- support-хранилище через `support_bot.storage`

### Runtime / infra

- `systemd` unit: `amonora-dashboard-ui.service`
- `ExecStart`: `next start -H 127.0.0.1 -p 3001`
- prod env: `/etc/amonora-dashboard-ui.env`
- reverse proxy: `ops/nginx/amonora-dashboard.server.conf`

## 4. Из чего состоит

### Фронтовая структура

```text
dashboard/ui/
  package.json
  next.config.ts
  public/
    brand-icon.svg
    favicon.svg
  src/
    app/
      page.tsx
      layout.tsx
      globals.css
      login/page.tsx
      verify/page.tsx
      auth/
        request-code/route.ts
        verify/route.ts
      api/
        proxy/[...path]/route.ts
      (dashboard)/
        layout.tsx
        overview/page.tsx
        users/page.tsx
        servers/page.tsx
        traffic/page.tsx
        payments/page.tsx
        support/page.tsx
        settings/page.tsx
        knowledge/page.tsx
    components/
      app-shell.tsx
      providers.tsx
      query-state.tsx
      theme-provider.tsx
      toast-center.tsx
      ui.tsx
    hooks/
      use-dashboard.ts
    lib/
      api.ts
      types.ts
      utils.ts
```

### Backend и infra-файлы, без которых UI Панели управления не работает

```text
dashboard/
  main.py
  v2_data.py
  services.py

ops/
  systemd/amonora-dashboard-ui.service
  env/amonora-dashboard-ui.env
  nginx/amonora-dashboard.server.conf
```

## 5. Базовая архитектура

### Поток данных

```text
Browser
  -> Next.js pages
  -> /api/proxy/dashboard/api/v2/*
  -> FastAPI backend on 127.0.0.1:8088
  -> DB / support storage / server metrics / docs source
```

### Что делает каждый слой

| Слой | Ответственность |
| --- | --- |
| `dashboard/ui` | UI, layout, forms, charts, polling, local state |
| `dashboard/ui/src/app/api/proxy/[...path]/route.ts` | проксирование frontend-запросов в backend |
| `dashboard/main.py` | HTTP endpoints `/dashboard/api/v2/*` |
| `dashboard/v2_data.py` | сборка payload-ов для страниц |
| `dashboard/services.py` | инфраструктурные операции, session/auth, docs, metrics, service status, logs, payments, support helpers |

### Важный принцип реализации

`Панель управления UI` почти не хранит собственную логику предметной области.  
Основная доменная логика остаётся в Python-контуре:

- доступ пользователя;
- тарифы;
- устройства;
- серверные снапшоты;
- платежи и финансы;
- support-операции;
- документация;
- admin session model.

## 6. Auth и session flow

### Вход

1. Пользователь открывает `/login`.
2. Форма уходит в `dashboard/ui/src/app/auth/request-code/route.ts`.
3. Этот route вызывает backend `POST /dashboard/api/v2/auth/request-code`.
4. Backend проверяет логин/пароль и отправляет код в Telegram через `@amonora_control_bot`.
5. Пользователь вводит код на `/verify`.
6. `dashboard/ui/src/app/auth/verify/route.ts` вызывает `POST /dashboard/api/v2/auth/verify`.
7. Backend возвращает session cookie.
8. Next route прокидывает cookie в браузер и редиректит на `/overview`.

### Session behavior

- dashboard layout проверяет `/session`;
- если сессии нет, идёт `router.replace("/login")`;
- idle timeout берётся из backend settings;
- в `AppShell` есть авто-logout по бездействию;
- при `401` frontend принудительно уводит на `/login`.

### Дополнительно

- у админа есть profile overlay;
- можно загрузить аватар через `/dashboard/api/v2/profile/avatar`;
- logout делается через `/dashboard/api/v2/auth/logout`.

## 7. Навигация и shell

Главный shell собирается в `AppShell`.

Он включает:

- левый sidebar с разделами;
- global search;
- notifications drawer;
- переключатель темы;
- profile overlay;
- logout;
- session guard-блок;
- toast-уведомления;
- sticky header.

Что есть в shell функционально:

- глобальный поиск по пользователям, серверам, платежам и support;
- всплывающие toast-уведомления для новых alert/payment событий;
- локальный счётчик unread в уведомлениях;
- light/dark theme через `localStorage`;
- авто-разлогин при бездействии.

## 8. Карта страниц и функций

### 8.1. `/overview`

Источник:

- hook: `useOverview()`
- backend: `GET /dashboard/api/v2/overview`
- frontend refetch: каждые `20` секунд
- backend cache: `15` секунд

Что показывает:

- KPI:
  - всего пользователей;
  - активный доступ;
  - активные устройства;
  - выручка за 30 дней;
  - серверы online.
- блок `Структура базы и тарифов`
- блок `Срез по тарифам`
- график трафика по нодам
- график новых пользователей и выручки
- график CPU/RAM/Disk по нодам
- rail alert-ов
- последние платежи
- последние действия админов

Как строится `Срез по тарифам`:

- backend считает `latest confirmed tariff` по пользователю;
- `paid_active` с известным `tariff_code` получает название тарифа, например `1 месяц`;
- `paid_active` без подтверждённого тарифа попадает в `Платный доступ`;
- `trial_active` даёт `Пробный период`;
- `trial_used` без доступа даёт `Пробный уже был`;
- иначе `Без тарифа`.

Плюс раздела:

- даёт быстрый live summary по прод-контуру;
- собирает и бизнес-метрики, и операционные сигналы;
- хорошо подходит как entry point для админа.

Ограничения:

- часть данных агрегируется не из materialized view, а на лету;
- точность близка к near-real-time, но не к truly-live;
- статусная плашка в header `Система в норме` сейчас статическая, а не вычисляемая.

### 8.2. `/users`

Источники:

- hook: `useUsers(q)` + `useUserDetail(user_id)`
- backend:
  - `GET /dashboard/api/v2/users`
  - `GET /dashboard/api/v2/users/{user_id}`

Что умеет:

- поиск по `Telegram ID`, `username`, `user id`;
- список пользователей со статусом, планом, числом устройств, страной, датой доступа;
- detail panel `User 360`;
- выдать пробный период;
- снять тариф и доступ;
- продлить доступ на N дней;
- сменить preferred protocol;
- создать устройство;
- удалить устройство;
- удалить пользователя вместе с VPN-данными;
- показать платежи и support context.

Что важно по логике:

- synthetic/test users отфильтровываются;
- страна берётся по устройствам;
- доступ вычисляется через `bot.utils.access`;
- trial/paid/block status идут из существующей модели пользователя.

Плюсы:

- реально рабочий операторский экран, а не просто read-only;
- совмещает тариф, устройства, платежи и support history;
- есть прямые admin actions без перехода в старую панель.

Недочёты:

- список без пагинации;
- privileged actions видны в UI шире, чем реально разрешены ролью, и часть контроля уходит в backend `403`;
- кнопка `Продлить` в users-админке меняет именно доступ по дням, а не создаёт платёжную запись;
- нет отдельного встроенного выбора тарифа при ручном продлении.

### 8.3. `/servers`

Источники:

- hook: `useServers(server_id, force)`
- backend:
  - `GET /dashboard/api/v2/servers`
  - `GET /dashboard/api/v2/servers/{server_id}`
  - `POST /dashboard/api/v2/servers/{server_id}/status`

Что показывает:

- summary по нодам;
- карточки серверов;
- CPU / RAM / Disk график;
- активные устройства;
- throughput;
- ping;
- load average;
- service pills;
- provider / IP / статус.

Что умеет:

- открыть detail panel по ноде;
- руками снять свежий snapshot `force=1`;
- менять статус managed server: `active / maintenance / disabled`;
- создавать managed server через backend API.

Плюсы:

- хороший operational view по Germany / Estonia;
- видно не только системную нагрузку, но и VPN-side метрики;
- есть bypass cache для ручного refresh.

Недочёты:

- settings/service layer по-прежнему не видит все реальные prod-сервисы;
- список нод и VPN-метрики завязаны на текущий snapshot pipeline, а не на отдельную TSDB;
- долгосрочной истории метрик нет, показан текущий срез.

### 8.4. `/traffic`

Источник:

- hook: `useTraffic()`
- backend: `GET /dashboard/api/v2/traffic`
- frontend refetch: `20` секунд
- backend cache: `20` секунд

Что показывает:

- текущую суммарную сетевую нагрузку;
- накопленный transfer;
- активные устройства;
- регионы online;
- ноды с отчётом;
- throughput по нодам;
- peak hours;
- split по регионам;
- pie по нодам;
- top countries.

Как считается:

- серверные snapshot-ы берутся из server metrics;
- активные устройства и регионы подтягиваются из users/clients;
- peak activity собирается эвристически по устройствам, пользователям, платежам, audit и support сообщениям за 24 часа.

Плюсы:

- даёт сетевой срез отдельно от общей overview-страницы;
- полезен для проверки нагрузки DE/EE split;
- наглядно объясняет, что это throughput нод, а не клиентский speedtest.

Недочёты:

- это не полноценная time-series аналитика;
- peak hours — производная operational activity, а не чистый netflow;
- нет drilldown по протоколам и нет длинного retention внутри UI.

### 8.5. `/payments`

Источники:

- hook: `usePayments(record_id)`
- backend:
  - `GET /dashboard/api/v2/payments`
  - `POST /dashboard/api/v2/payments`
  - `POST /dashboard/api/v2/payments/{record_id}/confirm`
  - `POST /dashboard/api/v2/payments/{record_id}/reject`
  - `GET/POST /dashboard/api/v2/payments/{record_id}/delete`
  - `GET /dashboard/api/v2/finance`
  - `POST /dashboard/api/v2/finance`
  - `POST /dashboard/api/v2/finance/{entry_id}/approve`
  - `POST /dashboard/api/v2/finance/{entry_id}/cancel`
  - `GET/POST /dashboard/api/v2/finance/{entry_id}/delete`
  - `POST /dashboard/api/v2/finance/report`

Что показывает:

- MRR;
- новые подписки;
- отклонённые платежи;
- ручную очередь;
- чистый финансовый результат;
- mix методов оплаты;
- таблицу платежей;
- finance ledger;
- detail выбранного платежа;
- detail связанной finance entry.

Что умеет:

- создать ручную платёжную запись;
- создать finance entry;
- подтвердить заявку;
- отклонить заявку;
- удалить платёж;
- провести / отменить / удалить финансовую запись;
- сгенерировать finance report в knowledge.

Плюсы:

- соединяет платежный журнал и операционный ledger;
- умеет работать с ручными СБП/крипто-кейсами;
- позволяет вести управленческий контур внутри панели.

Недочёты:

- создание manual payment идёт по raw `user_id`, что повышает риск человеческой ошибки;
- в UI причина reject сейчас фиксированная: `Отклонено из dashboard`;
- список без пагинации;
- роль `owner` требуется для части destructive действий, но UI не всегда заранее прячет их по permissions.

### 8.6. `/support`

Источники:

- hook: `useSupport(filter_mode, q, ticket_id)`
- backend:
  - `GET /dashboard/api/v2/support`
  - `GET /dashboard/api/v2/support/{ticket_user_id}`
  - `POST /dashboard/api/v2/support/{ticket_user_id}/assign`
  - `POST /dashboard/api/v2/support/{ticket_user_id}/transfer`
  - `POST /dashboard/api/v2/support/{ticket_user_id}/reply`
  - `POST /dashboard/api/v2/support/{ticket_user_id}/close`

Что умеет:

- фильтровать очередь: `all / new / in_progress / closed / mine`;
- искать по пользователю или сообщению;
- открывать диалог;
- отвечать пользователю;
- брать тикет на себя;
- передавать другому админу;
- закрывать тикет;
- видеть linked payments и payment counts.

Плюсы:

- позволяет работать по support без постоянного переключения в Telegram;
- связка support + payments сильно ускоряет ручную обработку;
- polling каждые `12` секунд подходит для операторского режима.

Недочёты:

- модель тикета завязана на `ticket_user_id`, то есть фактически на пользователя;
- UI не показывает богатую SLA-модель, статусы простые;
- нет отдельной многопоточной модели обращений на одного клиента.

### 8.7. `/knowledge`

Источники:

- hook: `useKnowledge(doc)`
- backend:
  - `GET /dashboard/api/v2/knowledge`
  - `POST /dashboard/api/v2/settings/docs/report`

Что умеет:

- показать manifest и список статей;
- искать по названиям/summary/slug;
- открыть HTML-рендер markdown;
- открыть GitHub source и raw markdown;
- сгенерировать operations report;
- показывать source label: `GitHub`, `Локальная копия`, `Сгенерированный отчёт`.

Как работает источник:

- по умолчанию docs тянутся из GitHub branch `develop`;
- если GitHub недоступен или manifest не грузится, есть fallback на локальную папку `documentation`;
- generated docs публикуются в ту же knowledge-модель.

Очень важный текущий operational note:

- репозиторий уже переведён в `private`;
- код документации по умолчанию смотрит в публичные `github.com` и `raw.githubusercontent.com`;
- из-за этого GitHub-source режим может перестать обновляться без авторизации;
- fallback на локальную копию в коде есть, так что сам раздел не обязан упасть, но источник может стать `Локальная копия`.

### 8.8. `/settings`

Источники:

- hook: `useSettings()`
- backend:
  - `GET /dashboard/api/v2/settings`
  - `POST /dashboard/api/v2/settings/services/action`
  - `POST /dashboard/api/v2/settings/tariffs`
  - `POST /dashboard/api/v2/settings/env`
  - `POST /dashboard/api/v2/settings/docs/report`

Вкладки:

- `Платежи`
- `API keys`
- `Серверы`
- `Боты`
- `Тарифы`
- `Services & env`

Что умеет:

- показать активные и скрытые способы оплаты;
- показать managed servers;
- показать masked API keys;
- показать service statuses;
- читать journal tail;
- отправлять `restart` и `status` action для сервисов;
- редактировать `.env`;
- редактировать тарифы;
- смотреть audit trail.

Плюсы:

- собран operational toolbox в одном месте;
- можно менять тарифы без ручной правки файла;
- есть masked env snapshot и audit trail.

Крупные ограничения:

- service controls сейчас знают только:
  - `amonora-bot.service`
  - `amonora-support-bot.service`
  - `amonora-dashboard.service`
- они не знают про:
  - `amonora-dashboard-ui.service`
  - `nginx`
  - другие prod units
- то есть раздел `Services & env` не покрывает весь реальный новый контур.

Дополнительные нюансы:

- `Очистить` лог в UI чистит только локальный preview, не `journalctl`;
- env-изменения очень мощные и рискованные, отдельного approval flow нет;
- UI tabs видны всем ролям, а не только тем, кому реально можно мутировать данные.

## 9. API-карта v2

### Auth / profile

- `POST /dashboard/api/v2/auth/request-code`
- `POST /dashboard/api/v2/auth/verify`
- `POST /dashboard/api/v2/auth/logout`
- `POST /dashboard/api/v2/profile/avatar`
- `GET /dashboard/api/v2/session`

### Search / notifications / overview

- `GET /dashboard/api/v2/search`
- `GET /dashboard/api/v2/notifications`
- `GET /dashboard/api/v2/overview`

### Users

- `GET /dashboard/api/v2/users`
- `GET /dashboard/api/v2/users/{user_id}`
- `POST /dashboard/api/v2/users/{user_id}/trial`
- `POST /dashboard/api/v2/users/{user_id}/extend`
- `POST /dashboard/api/v2/users/{user_id}/block`
- `POST /dashboard/api/v2/users/{user_id}/clear-access`
- `POST /dashboard/api/v2/users/{user_id}/protocol`
- `POST /dashboard/api/v2/users/{user_id}/devices`
- `POST /dashboard/api/v2/users/{user_id}/devices/{device_id}/delete`
- `GET/POST /dashboard/api/v2/users/{user_id}/delete`

### Servers / traffic

- `GET /dashboard/api/v2/servers`
- `GET /dashboard/api/v2/servers/{server_id}`
- `POST /dashboard/api/v2/servers`
- `POST /dashboard/api/v2/servers/{server_id}/status`
- `GET /dashboard/api/v2/traffic`

### Payments / finance

- `GET /dashboard/api/v2/payments`
- `POST /dashboard/api/v2/payments`
- `POST /dashboard/api/v2/payments/{record_id}/confirm`
- `POST /dashboard/api/v2/payments/{record_id}/reject`
- `GET/POST /dashboard/api/v2/payments/{record_id}/delete`
- `GET /dashboard/api/v2/finance`
- `POST /dashboard/api/v2/finance`
- `POST /dashboard/api/v2/finance/{entry_id}/approve`
- `POST /dashboard/api/v2/finance/{entry_id}/cancel`
- `GET/POST /dashboard/api/v2/finance/{entry_id}/delete`
- `POST /dashboard/api/v2/finance/report`

### Support

- `GET /dashboard/api/v2/support`
- `GET /dashboard/api/v2/support/{ticket_user_id}`
- `POST /dashboard/api/v2/support/{ticket_user_id}/assign`
- `POST /dashboard/api/v2/support/{ticket_user_id}/transfer`
- `POST /dashboard/api/v2/support/{ticket_user_id}/reply`
- `POST /dashboard/api/v2/support/{ticket_user_id}/close`

### Settings / knowledge

- `GET /dashboard/api/v2/settings`
- `GET /dashboard/api/v2/knowledge`
- `POST /dashboard/api/v2/settings/services/action`
- `POST /dashboard/api/v2/settings/tariffs`
- `POST /dashboard/api/v2/settings/env`
- `POST /dashboard/api/v2/settings/docs/report`

## 10. Polling и cache-профиль

### Frontend refetch intervals

| Раздел | Интервал |
| --- | ---: |
| `notifications` | `12s` |
| `overview` | `20s` |
| `servers` | `20s` |
| `traffic` | `20s` |
| `payments` | `30s` |
| `support` | `12s` |
| `settings` | без частого polling |
| `knowledge` | без частого polling |

### Backend cache TTL

| Endpoint family | TTL |
| --- | ---: |
| `search` | `10s` |
| `notifications` | `12s` |
| `overview` | `15s` |
| `users` | `20s` |
| `user-detail` | `15s` |
| `servers` | `15s` |
| `traffic` | `20s` |
| `payments` | `20s` |
| `support` | `8s` |
| `settings` | `45s` |
| `knowledge` | `45s` |

Что это означает practically:

- панель near-real-time;
- часть изменений видна с задержкой `8-45` секунд;
- force refresh реализован не везде;
- много экранов одновременно создают постоянный polling-profile.

## 11. Источники данных

### Основные доменные таблицы и модели

- `User`
- `VpnClient`
- `PaymentRecord`
- `FinanceEntry`
- `DashboardAdmin`
- `DashboardSession`
- `DashboardAuditLog`
- `ManagedServer`
- `SupportTicketMessage`

### Где собирается payload

| Payload | Основная функция |
| --- | --- |
| session | `get_v2_session_payload` |
| overview | `get_v2_overview_payload` |
| users | `get_v2_users_payload` |
| user detail | `get_v2_user_detail_payload` |
| servers | `get_v2_servers_payload` |
| traffic | `get_v2_traffic_payload` |
| payments | `get_v2_payments_payload` |
| support | `get_v2_support_payload` |
| notifications | `get_v2_notifications_payload` |
| search | `get_v2_search_payload` |
| settings | `get_v2_settings_payload` |
| knowledge | `get_v2_knowledge_payload` |

### Что важно по data-логике

- synthetic users с префиксами `manual_payment_`, `smoke_`, `test_`, `debug_`, `seed_` исключаются из части аналитики;
- доступ пользователя считается через общую bot access-логику;
- plan label зависит от access status и последнего подтверждённого тарифа;
- support counts и server metrics втягиваются в overview и notifications;
- knowledge использует manifest + markdown render.

## 12. Сильные стороны

1. Новый UI реально отделён от старого backend-контура, но не ломает существующую бизнес-логику.
2. Покрытие широкое: users, servers, traffic, payments, support, settings, knowledge.
3. Есть typed payloads и понятный data contract между frontend и backend.
4. Встроены polling, search, notifications, toasts и session guard.
5. Есть knowledge hub с generated reports и local fallback.
6. Legacy routing уже учтён через `nginx`, поэтому миграция идёт без жёсткого разрыва.
7. Панель годится не только для просмотра, но и для реальных операторских действий.

## 13. Слабые стороны и недочёты

1. Большая часть payload builder-ов работает через полную загрузку таблиц `User/VpnClient/PaymentRecord` в память и дальнейшую Python-агрегацию. Для текущего масштаба это терпимо, но масштабируется хуже, чем paginated/SQL-first подход.
2. Во многих списках нет пагинации: users, payments, support queue, finance entries.
3. UI не полностью role-aware: часть кнопок и вкладок видна до backend-проверки прав.
4. `Settings -> Services & env` не покрывает реальный новый prod-контур целиком, потому что не знает про `amonora-dashboard-ui.service` и `nginx`.
5. В header есть статичная плашка `Система в норме`, которая не привязана к настоящему health state.
6. Состояние read/unread у уведомлений живёт только на клиенте и не хранится на сервере.
7. Payments reject flow в UI сейчас без нормального ввода причины.
8. Support-модель центрируется вокруг `ticket_user_id`, а не around multiple independent conversations.
9. `dashboard/ui/README.md` всё ещё описывает v2 как `preview`, хотя infra уже проксирует новые prod-маршруты на Next.js.
10. systemd unit для Next.js идёт под `User=root`, что operationally удобно, но не идеально с точки зрения минимальных привилегий.

## 14. Что ещё требует ручной проверки

На текущем контуре особенно стоит вручную прогонять:

- `Users`
- `Payments`
- `Support`
- `Settings`
- `Overview`
- `Notifications`
- knowledge source mode после перевода репозитория в `private`
- аналитические блоки типа `Срез по тарифам`

Причина:

- часть вещей уже внедрялась быстро на живом сервере;
- не все сценарии, особенно destructive/admin actions, явно покрыты спокойным финальным regression QA.

## 15. Плюсы и минусы коротко

### Плюсы

- современный, цельный интерфейс;
- сильное покрытие операционных сценариев;
- повторно использует уже работающую backend-логику;
- хорошо подходит как центр управления экосистемой Amonora.

### Минусы

- heavy server-side aggregation;
- неполное role-aware скрытие действий;
- сервисный раздел пока не полностью синхронизирован с реальным infra-слоем;
- knowledge source now operationally чувствителен к private GitHub.

## 16. Ключевые файлы, которые надо знать

| Файл | Зачем нужен |
| --- | --- |
| `dashboard/ui/src/app/(dashboard)/overview/page.tsx` | overview UI и виджет `Срез по тарифам` |
| `dashboard/ui/src/app/(dashboard)/users/page.tsx` | users list, user actions, devices |
| `dashboard/ui/src/app/(dashboard)/servers/page.tsx` | nodes, live metrics, status actions |
| `dashboard/ui/src/app/(dashboard)/traffic/page.tsx` | traffic analytics |
| `dashboard/ui/src/app/(dashboard)/payments/page.tsx` | payments + finance |
| `dashboard/ui/src/app/(dashboard)/support/page.tsx` | support queue и dialog ops |
| `dashboard/ui/src/app/(dashboard)/settings/page.tsx` | tariffs, services, env, keys |
| `dashboard/ui/src/app/(dashboard)/knowledge/page.tsx` | docs hub |
| `dashboard/ui/src/components/app-shell.tsx` | shell, search, notifications, profile |
| `dashboard/ui/src/hooks/use-dashboard.ts` | все frontend data hooks |
| `dashboard/ui/src/lib/api.ts` | API envelope и proxy fetch logic |
| `dashboard/main.py` | v2 API endpoints |
| `dashboard/v2_data.py` | сборка page payload-ов |
| `dashboard/services.py` | sessions, docs, metrics, services, logs, support helpers |
| `ops/systemd/amonora-dashboard-ui.service` | запуск Next.js в проде |
| `ops/nginx/amonora-dashboard.server.conf` | маршрутизация между landing, backend и v2 |

## 17. Итог

`Панель управления UI` уже выглядит как реальный основной admin frontend Amonora, а не просто экспериментальный preview.

Главные достоинства:

- цельный интерфейс;
- широкое покрытие операционной рутины;
- хорошая интеграция с существующим backend-контуром.

Главные системные долги:

- data aggregation и отсутствие пагинации;
- неполное совпадение UI/permissions/service map;
- зависимость knowledge от внешнего GitHub source при том, что репозиторий уже закрыт.

Если смотреть на проект прагматично, `Панель управления UI` уже полезен и рабочий, но ему ещё нужен спокойный technical hardening pass:

- performance/scaling;
- role-aware UX;
- полный prod-service inventory;
- regression QA по ключевым сценариям.
