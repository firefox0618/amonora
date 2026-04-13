# ARCHITECTURE

## Что описывает этот документ

Этот документ фиксирует фактическую архитектуру проекта на текущем этапе.

Важно разделять два уровня:

- `Amonora` — экосистема сервисов, которую команда строит шире одного продукта;
- `Amonora` — текущий основной рабочий продукт внутри этой экосистемы.

Ниже описана архитектура именно текущего продукта `Amonora`.

## Архитектурная модель в одном абзаце

`Amonora` — это Telegram-first сервис доступа, где основной клиентский путь проходит через `@amonora_bot`, клиентская поддержка вынесена в отдельный `@amonora_support_bot`, внутренние системные уведомления и operational review живут в `@amonora_control_bot`, публичная витрина и user-level subscription page живут на `landing`, административная работа идёт через Панель управления (`dashboard` backend + `dashboard/ui` frontend), а ядро бизнес-логики и данные сосредоточены в Python backend-контуре и PostgreSQL.

## Архитектурный принцип на текущем этапе

По текущему состоянию проекта система развивается по модели:

- modular monolith first;
- extraction later.

Это значит:

- общая система пока живёт как связанный Python-контур;
- логика ещё не разрезана на отдельные сервисы;
- усложнение архитектуры должно происходить только после стабилизации текущего раннего прод-контура.

## Control plane и data plane

Для понимания системы полезно различать два логических слоя.

### Control plane

Это слой управления и принятия решений:

- `bot`
- `support_bot`
- `control_bot`
- `dashboard`
- `dashboard/ui`
- backend-логика
- admin/session/auth слой

### Data plane

Это слой, через который реально живёт VPN-доступ и инфраструктурная нагрузка:

- VPN-ноды
- `3x-ui`
- Xray / VPN runtime
- серверные маршруты и конфиги доступа

На текущем этапе control plane и data plane уже разделены по серверам, и это важный базовый принцип текущей архитектуры.

## Главные слои системы

Архитектурно проект можно разделить на четыре слоя:

1. `Core` — общая логика, модели и данные.
2. `Interfaces` — то, через что с системой взаимодействуют люди.
3. `Operations` — запуск, маршрутизация, обслуживание и эксплуатация.
4. `Infrastructure` — серверы и VPN-ноды, на которых всё это живёт.

## 1. Core

### backend

`backend` — это общее ядро продукта.

Здесь находятся:

- общие модели;
- схема базы данных;
- базовые доменные сущности;
- слой, на который опираются другие Python-сервисы.

С апреля 2026 года schema auto-apply больше не опирается на слепой повторный прогон всего списка `ALTER`-ов на каждый старт:

- core и dashboard используют общий registry применённых schema-steps в PostgreSQL;
- каждый schema-step получает стабильный ключ;
- шаг считается применённым только после фактического эффекта, а не просто после попытки выполнить SQL.

Без этого слоя не работают:

- `bot`
- `support_bot`
- `control_bot`
- `dashboard`

### dashboard как часть core

Хотя `dashboard` воспринимается как админка, фактически он сейчас является не только интерфейсом, но и важной частью ядра.

Именно здесь живут:

- административный backend;
- API;
- auth/session модель админки;
- часть управленческой логики по пользователям, платежам, support и серверам;
- backend для `dashboard/ui`.

Поэтому текущая архитектура не сводится к формуле “`backend` отдельно, `dashboard` только как UI”.  
Сейчас `dashboard` — это и интерфейс, и важный сервисный слой.

### Source of truth

Главный source of truth — PostgreSQL.

В БД хранятся:

- пользователи;
- подписки и доступы;
- устройства;
- платежи;
- тикеты поддержки;
- административные сущности;
- часть служебных настроек и журналов;
- лёгкий analytics-ledger для `канал -> бот -> конфиг -> оплата -> первое подключение`, который живёт в тех же PostgreSQL tables `analytics_*`, а не в отдельном heavy telemetry stack.

`dashboard/ui` не является источником истины.
`landing` тоже не является источником истины.  
Они используют общую backend-логику и общую БД.

Для операторской аналитики с апреля 2026 года добавлен отдельный минимальный contour:

- `analytics_user_attribution` и `analytics_events` хранят low-volume business events и first/last source attribution;
- `analytics_daily_*`, `analytics_daily_payment_failure_reasons`, `analytics_daily_attribution_integrity` и `analytics_cohort_retention` — это pre-aggregated rollup tables для чтения, а не raw operational joins; compatibility rollups `analytics_daily_stage_segments` и `analytics_daily_revenue_segments` остаются в схеме, но строгий operator suite больше не зависит от них как от главного источника истины;
- `analytics_hourly_ops_incidents` и `analytics_hourly_ops_snapshots` дают отдельный pre-aggregated ops слой для repair/incidents/runtime давления;
- `analytics_runtime_status` хранит machine-readable freshness / restore / ops status rows, включая `source_key_integrity` и `growth_active_users`, на которых могут висеть Grafana panels и alert rules;
- growth/payment analytics теперь явно различают `subscription_activated` и `subscription_renewed`, а revenue rollups дополнительно маркируют `payment_kind = new / renewal / other / unknown`, чтобы новые оплаты и продления не смешивались в одной денежной метрике;
- UI-suite использует словарь `connection_started / connection_ready`, но SQL-rollups продолжают читать исторические `onboarding_started / onboarding_completed` как backward-compatible aliases;
- `amonora-analytics-refresh` как 10-минутный oneshot/timer обновляет rollups incremental-path'ом;
- primary PostgreSQL и `amonora-analytics-refresh` остаются на `core`;
- `Grafana OSS` вынесена на Estonia infra-host и читает только `analytics_*` tables через отдельного read-only PostgreSQL role и локальный SSH tunnel к `core`, не открывая PostgreSQL наружу;
- `Grafana OSS` не должна напрямую строить dashboard panels по `users`, `payment_records`, `vpn_client_activations`, `finance_entries`, `control_notification_events` или `channel_post_touches`;
- repo-managed suite и repo-managed alerting лежат в `ops/grafana/`, а доставку alert payload из Grafana в Telegram control контур делает guarded internal webhook на `core`, а не прямой внешний чат-интегратор.

## 2. Interfaces

### bot

`bot` — главный пользовательский интерфейс текущего продукта.

Через него клиент:

- получает пробный доступ;
- управляет подпиской;
- создаёт устройства;
- выбирает страну и протокол;
- получает ключи для `VLESS` / `Trojan` и QR;
- видит денежный `Баланс` и тратит его в RUB-платежах;
- инициирует auto `СБП` и крипто-оплаты через `Platega`, получая checkout-link и user-side `Проверить оплату`;
- инициирует поддержку.

Это главный продуктовый вход для клиента.

### support_bot

`support_bot` — отдельный интерфейс поддержки.

Через него идут:

- обращения клиентов;
- диалоги;
- тикеты;
- медиавложения клиентов и операторов;
- часть support-операций команды.

Граница этого слоя:

- `support_bot` не должен получать dashboard auth-коды;
- `support_bot` не должен быть payment-review консолью;
- `support_bot` не должен быть маршрутом для системных node / infra alerts.

### control_bot

`control_bot` — отдельный internal Telegram-интерфейс для команды.

Через него идут:

- системные уведомления и event log;
- review ручных оплат;
- коды входа в админку;
- node / infra alerts;
- lifecycle и access события по пользователям.

После полного redesign этот слой стал не только read-only operational feed, но и owner-oriented control surface:

- `Настройки` с per-admin notification preferences;
- `Рассылка / Триггеры` с admin pushes, user campaigns, шаблонами и DB-driven trigger rules;
- active dashboard sessions summary;
- отдельный campaign/delivery слой для user/admin messaging.

Он не заменяет `dashboard`, а дополняет его как отдельный operational surface.

### landing

`landing` — публичная веб-витрина продукта.

Он нужен для того, чтобы:

- объяснить, что такое `Amonora`;
- привести пользователя в бота;
- в случаях, когда Telegram недоступен напрямую, выдать ограниченный bridge-ключ на `24 часа`, чтобы пользователь смог открыть Telegram и продолжить основной сценарий в `@amonora_bot`;
- показать тарифы и сценарий подключения;
- отдать правовые страницы;
- принять provider callback для auto `СБП/крипты` через `Platega`, не превращаясь в отдельную публичную веб-кассу;
- отдать tokenized user-level страницу подписки на `client.amonoraconnect.com/<token>`, где браузер получает HTML-страницу, а Happ импортирует feed с того же URL; compatibility route `client.amonoraconnect.com/sub/<token>` остаётся только как fallback seam;
- обслужить часть публичного web-контура.

Важно:

- legacy `POST /vpn/activate` больше не считается рабочей частью архитектуры продукта;
- Estonia больше не выступает продуктовым VPN-регионом и используется как infra-host.

### dashboard

`dashboard` — административный интерфейс и backend-контур админки.

Сейчас в нём сосуществуют:

- FastAPI backend;
- API для нового фронтенда;
- служебные административные операции;
- compatibility redirects и узкий auth/static seam для исторических admin entrypoints.

Важно:

- backend-rendered `dashboard.html` больше не считается активным основным shell админки;
- основной рабочий UI теперь живёт в `dashboard/ui` на корневых admin-маршрутах;
- исторические `/dashboard/*` page-routes должны восприниматься как переходный redirect-layer, а не как отдельная живая панель.

### Панель управления UI

`dashboard/ui` — новый frontend админки на Next.js.

Он:

- является текущим основным UI для команды;
- не хранит самостоятельную доменную логику;
- работает поверх `dashboard` API;
- зависит от backend-слоя админки, а не заменяет его;
- строится вокруг role-aware control-center surfaces: `overview`, `users`, `payments`, `support`, `servers`, `traffic`, `audit`, `knowledge`, `settings`;
- должен считать backend permission checks источником истины для role/model boundaries, а не пытаться замещать их одним frontend gating.

Ключевой принцип:

`dashboard/ui` — это интерфейсный слой, а не отдельное ядро.

## 3. Operations

### ops

`ops` — эксплуатационный слой проекта.

Здесь находятся:

- `systemd`-юниты;
- `nginx`-конфигурация;
- env-файлы;
- watchdog и напоминания;
- служебные скрипты и runtime-настройки.

После redesign `Amonora Control` сюда также относится shared messaging worker:

- `amonora-access-reminders.service/.timer`

Он больше не является только legacy reminder-скриптом.
Сейчас это общий 5-минутный worker для:

- scheduled user/admin campaigns;
- DB-driven automatic triggers;
- inactivity / access / trial follow-up logic.

Это не бизнес-логика, но без этого не работает продовый запуск.

### backups

`backups` — эксплуатационная папка для резервных копий.

Это не часть архитектурного ядра, но часть операционного контура.

## 4. Infrastructure

### Backend-сервер

На backend-сервере размещены:

- PostgreSQL;
- основной бот;
- support-бот;
- control-бот;
- dashboard backend;
- landing;
- `nginx`;
- SSH-туннели к VPN-панелям.

Это основной backend-контур продукта.

### VPN-ноды

VPN-ноды вынесены отдельно.

На них живут:

- VPN-контур;
- `3x-ui`;
- Docker / container runtime;
- SSH.

На них не должны жить:

- боты;
- dashboard;
- PostgreSQL;
- основной backend-контур.

Это сделано для того, чтобы не смешивать клиентскую и административную часть с VPN-нагрузкой.

## Будущие модули экосистемы

На уровне стратегии экосистема `Amonora` смотрит шире текущего VPN-контура.

Следующие направления рассматриваются как будущие слои роста, а не как уже реализованная часть текущей runtime-архитектуры:

- Automations
- Data
- AI

Важно:

это future architecture direction, а не описание текущего production state.

## Главные зависимости

В упрощённом виде зависимости такие:

- `bot` -> `backend` -> PostgreSQL
- `support_bot` -> `backend` -> PostgreSQL
- `control_bot` -> `backend` -> PostgreSQL
- `dashboard` -> `backend` + PostgreSQL + support storage/service layer
- `dashboard/ui` -> `dashboard` API
- `landing` -> общая Python-логика + PostgreSQL + публичная статика client-app
- `ops` -> обслуживает запуск и маршрутизацию всех runtime-сервисов

## Упрощённая схема связей

```text
landing -> bot / support_bot / public pages / client subscription page+feed
bot -> backend -> PostgreSQL
support_bot -> backend -> PostgreSQL
control_bot -> backend -> PostgreSQL
dashboard -> backend + PostgreSQL
dashboard/ui -> dashboard API -> PostgreSQL
ops -> systemd / nginx / env / runtime
VPN nodes -> external infrastructure managed through server and admin flows
```

## Главный продуктовый поток

Основной пользовательский путь сейчас выглядит так:

1. Пользователь приходит через `landing` или сразу в `@amonora_bot`.
2. Если Telegram не открывается напрямую, `landing` может выдать временный bridge-ключ на `24 часа`; после этого пользователь всё равно переходит в `@amonora_bot`.
3. Входит в основной bot и запускает сценарий доступа.
4. Бот обращается к общей backend-логике.
5. Система проверяет доступ, подписку, тариф, устройство и нужную VPN-ноду.
6. Данные сохраняются в PostgreSQL.
7. Пользователь получает конфиг, QR, статус доступа или результат платежного действия.
8. При необходимости пользователь может из `Личного кабинета` открыть отдельную user-level страницу подписки на `client.amonoraconnect.com/<token>` и импортировать account-level feed через тот же URL в Happ по QR или copy-link, не ломая текущий device-flow.
9. Если нужен человек, поток уходит в `support_bot`.
10. Внутренние системные события и review ручных оплат идут в `control_bot`.
11. Команда управляет теми же сущностями через `dashboard` и `dashboard/ui`.

## Что запускается отдельно

Отдельными runtime-контурами сейчас являются:

- `bot`
- `support_bot`
- `control_bot`
- `dashboard`
- `dashboard/ui`
- `landing`
- служебные процессы из `ops`

При этом:

- `dashboard/ui` работает как отдельный frontend-сервис;
- `dashboard` работает как отдельный backend/API админки;
- `landing` обслуживает публичный веб-контур;
- все они сходятся в общей data-модели и общей БД.

## Что является ядром, а что обвязкой

### Ядро

К ядру текущего продукта относятся:

- `backend`
- PostgreSQL
- значимая backend-логика внутри `dashboard`

### Интерфейсная обвязка

К интерфейсной обвязке относятся:

- `bot`
- `support_bot`
- `control_bot`
- `landing`
- `dashboard/ui`
- UI-часть `dashboard`

### Эксплуатационная обвязка

К эксплуатационной обвязке относятся:

- `ops`
- `backups`

## Где в архитектуре есть историческая сложность

Сейчас главный архитектурный переходный участок — это админка.

Причина в том, что:

- `dashboard` уже не просто старый UI, а полноценный backend-слой;
- `dashboard/ui` уже используется как основной новый интерфейс;
- legacy page-маршруты больше не рендерят старый shell и выступают как compatibility redirects.

Поэтому в архитектуре админки сейчас есть смешанный период:

- новый UI уже работает;
- старый backend всё ещё обязателен;
- legacy page-seam уже не должен считаться основным рабочим путём, но backend/auth/API seam по-прежнему остаётся load-bearing.

## Итоговая схема

Если описать архитектуру совсем кратко:

- `Amonora` — это экосистема;
- `Amonora` — текущий основной продукт;
- клиентский вход идёт через `bot`;
- поддержка идёт через `support_bot`;
- внутренние системные уведомления и payment review идут через `control_bot`;
- публичная витрина живёт в `landing`;
- админский backend живёт в `dashboard`;
- админский frontend живёт в `dashboard/ui`;
- общее ядро и данные сосредоточены в Python-контуре и PostgreSQL;
- `ops` обеспечивает запуск и продовую эксплуатацию;
- VPN-ноды живут отдельно от backend-контура.
