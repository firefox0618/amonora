# AMONORA — CONTROL CENTER VISION (FULL DETAILED SPEC)

Дата: 19 марта 2026  
Версия: 1.0  
Статус: Strategic Product / UX / Operations Specification

---

# 0. НАЗНАЧЕНИЕ ДОКУМЕНТА

Этот документ фиксирует **целевое состояние панели управления Amonora**.

Не текущую реализацию.  
Не обзор того, что уже есть.  
А **подробно сформированную модель того, какой панель должна стать**, если Amonora развивается как:

- VPN / Access-продукт
- automation-платформа
- data / parsing / monitoring-продукт
- AI / assistant-платформа
- единая экосистема с общим ядром

Этот документ нужен, чтобы:

- перестать думать о панели как о “наборе экранов”;
- превратить её в **единый центр управления экосистемой**;
- понимать, какие разделы обязательны;
- понимать, какие действия допустимы и как они должны работать;
- строить панель не хаотично, а как продукт.

---

# 1. ГЛАВНАЯ ИДЕЯ ПАНЕЛИ

## 1.1. Что такое Amonora Control Center

Amonora Control Center — это **единый центр управления платформой Amonora**.

Он нужен не только для управления VPN, а для управления всей системой:

- пользователями;
- подписками;
- доступом;
- устройствами;
- нодами;
- support;
- платежами;
- продуктами экосистемы;
- automation-задачами;
- data-источниками;
- AI-модулями;
- инцидентами;
- конфигурацией;
- документацией;
- безопасными административными действиями.

---

## 1.2. Каким должен быть Control Center

Панель должна ощущаться как:

- **операционный центр**;
- **SaaS admin console**;
- **NOC-light для инфраструктуры**;
- **CRM-light для пользователей и платежей**;
- **control plane для экосистемы**.

Панель не должна ощущаться как:

- набор случайных форм;
- интерфейс “для разработчика только потому что больше некому”;
- страница, где кнопки существуют сами по себе;
- место, где опасные действия совершаются без контекста и подтверждения.

---

## 1.3. Главная ценность панели

Главная ценность панели — не “показать данные”.

Главная ценность:

> дать основателю и команде **контроль над экосистемой Amonora как над живой системой**

Это означает, что админ должен уметь:

- за 30–60 секунд понять общее состояние;
- быстро увидеть, где проблема;
- быстро открыть нужный объект;
- понять контекст объекта;
- выполнить действие;
- получить понятный результат;
- не сломать прод;
- видеть следствие своих действий;
- работать не только с VPN, но и с другими продуктами Amonora.

---

# 2. ОСНОВНЫЕ ПРИНЦИПЫ ДИЗАЙНА ПАНЕЛИ

---

## 2.1. Панель должна быть системной

Каждый раздел должен быть частью общей логики.

Например:

- пользователь связан с тарифом;
- тариф связан с платежами;
- платеж связан с подпиской;
- подписка связана с продуктом;
- продукт связан с entitlement;
- entitlement связан с доступом;
- доступ связан с устройством;
- устройство связано с нодой;
- нода связана с alerts;
- alert связан с support volume и incident log.

То есть система должна быть связана горизонтально, а не жить отдельными страницами.

---

## 2.2. Панель должна быть role-aware

Пользователь панели должен видеть:

- только те действия, которые ему доступны;
- только те риски, за которые он отвечает;
- только те зоны, где его роль нужна;
- только тот уровень доступа, который безопасен.

Кнопка не должна быть видна, если роль не может её выполнить.

---

## 2.3. Панель должна быть action-driven

Почти каждый экран должен отвечать на вопрос:

> “Что нужно сделать прямо сейчас?”

Не просто:
- “что вообще есть в базе”

А:
- где проблема
- что делать
- как быстро отреагировать

---

## 2.4. Панель должна быть безопасной

Любое опасное действие должно иметь:

- явное предупреждение;
- подтверждение;
- понятное описание последствий;
- результат;
- запись в audit log;
- по возможности — hint по откату.

---

## 2.5. Панель должна быть экосистемной

Нельзя проектировать её только под VPN.

Даже если VPN — первый и основной продукт, архитектура панели должна учитывать следующие модули:

- Access
- Automations
- Data
- AI

Чтобы потом не пришлось строить вторую, третью и четвёртую панели отдельно.

---

# 3. Amonora КАК ЭКОСИСТЕМА И КАК ЭТО ДОЛЖНО ОТРАЖАТЬСЯ В ПАНЕЛИ

---

## 3.1. Ядро платформы (Amonora Core)

Общее ядро:

- Users
- Auth
- Billing
- Entitlements
- Support
- Notifications
- Audit
- Docs / Knowledge
- Product registry

Все продукты используют это ядро.

Панель должна быть построена вокруг ядра, а не вокруг одного продукта.

---

## 3.2. Продуктовые модули Amonora

### Module 1 — Access
Что включает:
- VPN
- DNS
- Proxy
- доступ к регионам
- access-профили
- устройства

### Module 2 — Automations
Что включает:
- Telegram bots
- n8n flows
- auto-replies
- integrations
- workflow execution
- automation clients / projects

### Module 3 — Data
Что включает:
- parsing
- monitoring
- alerts
- source management
- data results
- scheduled jobs

### Module 4 — AI
Что включает:
- AI assistants
- content generation
- classification
- support AI
- prompt-driven actions
- AI quota / requests / outputs

Панель должна позволять подключать и управлять всеми этими модулями как частями одной платформы.

---

# 4. ИДЕАЛЬНАЯ ИНФОРМАЦИОННАЯ АРХИТЕКТУРА ПАНЕЛИ

---

# 4.1. Верхний уровень навигации

Я бы формировал панель так:

1. Dashboard  
2. Users  
3. Access  
4. Nodes  
5. Payments  
6. Support  
7. Products  
8. Automations  
9. Data  
10. AI  
11. Alerts  
12. Knowledge  
13. Settings  
14. Audit

Это не значит, что все пункты сразу должны быть активны в проде.  
Но именно так должна мыслиться итоговая структура.

---

# 4.2. Какие разделы обязательны прямо сейчас

На текущем этапе Amonora обязательны:

- Dashboard
- Users
- Access
- Nodes
- Payments
- Support
- Alerts
- Knowledge
- Settings
- Audit

---

# 4.3. Какие разделы должны быть предусмотрены как будущие

- Products
- Automations
- Data
- AI

Даже если пока они скрыты за feature flags или beta-access, структура панели должна быть готова к ним заранее.

---

# 5. ГЛАВНЫЙ ЭКРАН: DASHBOARD / COMMAND CENTER

---

## 5.1. Назначение

Главный экран должен быть **командным центром**.

Он нужен для того, чтобы:

- понять состояние платформы;
- увидеть риски;
- увидеть деньги;
- увидеть пользовательскую активность;
- увидеть операционные приоритеты;
- принять решение о следующем действии.

Главный экран не должен быть просто набором карточек “ради красоты”.

---

## 5.2. Структура главного экрана

### Блок A — Global System Health
Отображает состояние:

- Core Backend
- Database
- Dashboard Frontend
- Telegram Bot
- Support Bot
- Billing
- Germany Node
- Estonia Node
- Access Plane
- Support Queue
- Docs Source
- Automation Engine (когда появится)
- Data Jobs (когда появится)
- AI Layer (когда появится)

Статусы:
- OK
- Warning
- Critical
- Unknown
- Maintenance

Обязательно:
- короткая причина;
- время последнего обновления;
- переход на подробности.

---

### Блок B — Core Business KPIs
Показывает:

- всего пользователей
- активные пользователи
- активные устройства
- trial_active
- paid_active
- vip_active
- MRR
- выручка за 30 дней
- платежи в ожидании
- открытые тикеты
- новые пользователи за 7 дней
- churn / ушедшие доступы
- conversion trial → paid (когда появятся данные)

---

### Блок C — Action Queue / Requires Attention
Это один из самых важных блоков.

Показывает:

- pending payments
- new support tickets
- degraded nodes
- users with failed access
- expiring VIP users
- stale service snapshots
- docs source issues
- automation failures
- data job failures
- AI quota issues

Это должен быть блок “что делать прямо сейчас”.

---

### Блок D — Revenue & Product Snapshot
Показывает:

- revenue by product
- revenue by payment method
- revenue trend
- active subscriptions by product
- plan distribution
- access product vs automation revenue vs future products

Даже если пока revenue идёт в основном из VPN, панель должна быть готова к мультипродуктовой модели.

---

### Блок E — Access Overview
Показывает:

- активные access users
- устройства по регионам
- устройства по протоколам
- пользователи по нодам
- top problematic node
- active access profiles
- access incidents за 24 часа

---

### Блок F — Operations Overview
Показывает:

- последние критичные алерты
- последние admin actions
- последние deploy / config actions
- последние service restarts
- последние инциденты

---

### Блок G — Growth / Opportunity
Показывает:

- новые лиды по automation
- входящие диалоги / потенциальные клиенты
- активные automation deals
- новые подписки
- повторные платежи

Этот блок важен, потому что Amonora — не только ops, но и рост.

---

# 6. USERS — USER CONTROL HUB

---

## 6.1. Назначение

Раздел Users должен быть не просто списком пользователей, а **центром управления конкретным человеком внутри экосистемы**.

Он должен отвечать на вопросы:

- кто это;
- что у него куплено;
- что у него активировано;
- на каких продуктах он сидит;
- какие у него устройства;
- какие у него платежи;
- были ли обращения;
- есть ли проблемы;
- что можно сделать прямо сейчас.

---

## 6.2. Список пользователей

В списке должны быть:

- user_id
- telegram_id
- username
- display name
- status
- product entitlements
- active plan
- devices count
- regions / products
- latest payment
- latest support activity
- source / acquired_via (в будущем)
- created_at
- updated_at

Фильтры:
- all
- active
- inactive
- trial
- paid
- vip
- by product
- by region
- by protocol
- by risk / complaints
- by support status

Поиск:
- username
- telegram id
- internal user_id
- payment reference
- device label

---

## 6.3. User 360 view

При открытии пользователя должно быть видно:

### Identity
- имя
- username
- telegram id
- internal id
- дата регистрации
- acquired source (когда появится)
- теги

### Access Summary
- статус доступа
- текущие entitlement
- активный продукт
- тариф
- дата окончания
- device limit
- preferred protocol
- preferred region

### Devices
- список всех устройств
- статус
- продукт
- регион
- протокол
- inbound/profile
- дата создания
- last seen / recent activity (в будущем)
- QR / config / re-issue

### Payments
- история платежей
- pending
- confirmed
- rejected
- linked finance entries
- что именно было оплачено

### Support
- тикеты
- последние сообщения
- open / closed issues
- assigned admin

### Product Usage (в будущем)
- automation subscriptions
- active workflows
- data monitors
- AI usage / quota

### Risk / Notes
- notes от команды
- flags
- блокировки
- suspicious actions
- failed payments

---

## 6.4. Действия по пользователю

Разрешённые действия должны быть сгруппированы.

### Access actions
- выдать trial
- продлить доступ
- снять доступ
- сменить протокол
- сменить preferred region
- создать устройство
- удалить устройство
- перевыдать конфиг
- заблокировать пользователя

### Billing actions
- создать manual payment
- подтвердить pending payment
- отклонить payment с причиной
- привязать оплату к плану
- пересчитать entitlement

### Support actions
- открыть тикет
- передать тикет
- оставить note
- пометить как risky / VIP / manual review

### Ecosystem actions (в будущем)
- включить automation package
- включить data alerts
- выдать AI quota
- отключить продукт

Каждое действие должно иметь:
- confirm modal
- preview of effect
- success/failure message
- audit record

---

# 7. ACCESS — CONTROL PLANE ДЛЯ ДОСТУПА

---

## 7.1. Назначение

Access — это не просто “VPN”.

Это должен быть **раздел управления доступом как продуктом**.

Он отвечает за:

- доступ пользователей;
- access profiles;
- регионы;
- протоколы;
- inbound allocation;
- device issuance;
- health access plane;
- manual overrides.

---

## 7.2. Что должен включать раздел Access

### Subsection A — Profiles
Показывает:

- список access profiles
- legacy / active / experimental
- product linkage
- protocol
- network
- security
- node assignment
- new-user eligible or not
- deprecation status

Примеры профилей:
- DE legacy stable
- DE new stable
- EE legacy stable
- EE new stable
- Trojan fallback DE
- Trojan fallback EE
- future DNS access package
- future lite proxy package

---

### Subsection B — Allocation / Issuance
Показывает:

- какой профиль выдаётся по умолчанию
- какие профили доступны новым пользователям
- какие профили скрыты
- какая нода перегружена
- какие профили deprecated
- какие users сидят на каком профиле

Позволяет:
- включать / отключать profile for new issuance
- отмечать profile as beta
- ограничивать issuance to role or cohort
- переводить issuance strategy
- переводить node в maintenance mode

---

### Subsection C — Devices
Показывает:

- все устройства по access-продукту
- по продукту / региону / протоколу
- orphan devices
- deleted but not fully synced states
- profile distribution
- issued recently
- expiring soon

---

### Subsection D — Access Analytics
Показывает:

- devices by protocol
- devices by node
- users by node
- access incidents by node
- support tickets related to access
- failed issuance count
- migration readiness
- profile adoption

---

### Subsection E — Manual Operations
Позволяет:
- hand-assign profile
- reassign node
- disable profile
- mark node unavailable for new users
- force resync a device
- resync user access state
- run consistency check

---

## 7.3. Почему Access должен быть отдельным разделом

Если всё оставить размазанным по Users и Servers, у тебя никогда не появится **отдельная продуктовая логика доступа**.

А Amonora как экосистема должна уметь потом поддерживать:
- VPN
- DNS
- Proxy
- пакеты доступа
- разные access plans

Поэтому Access — это ядро продуктового control plane, а не побочный экран.

---

# 8. NODES — УПРАВЛЕНИЕ НОДАМИ И ИНФРАСТРУКТУРОЙ ДОСТУПА

---

## 8.1. Назначение

Nodes — это инфраструктурный раздел.

Он нужен для управления:

- VPN-нодами;
- access infrastructure;
- managed server health;
- capacity;
- maintenance;
- node role assignment.

---

## 8.2. Карточка ноды должна показывать

### Identity
- имя
- регион
- IP
- домен
- провайдер
- ASN
- тип
- роль: primary / fallback / experimental
- статус: active / maintenance / disabled

### System Health
- CPU
- RAM
- disk
- load average
- ping
- uptime
- last snapshot

### Access Metrics
- active users
- active devices
- clients count
- throughput
- profile assignment
- protocol mix

### Operational State
- alerts
- recent incidents
- config drift notes
- health rule triggered?
- maintenance flag?
- issue notes

---

## 8.3. Действия по ноде

- refresh snapshot
- mark maintenance
- disable for new users
- disable entirely
- change role
- add note
- open incident
- link to docs/runbook
- view historical alerts

---

## 8.4. История ноды

Очень важно хранить:
- деградации
- падения
- ручные изменения статуса
- когда была перегрузка
- когда была maintenance
- кто менял состояние

---

# 9. PAYMENTS — БИЛЛИНГ И ФИНАНСОВЫЙ КОНТУР

---

## 9.1. Назначение

Payments должен быть не только журналом записей, а **управляющим слоем биллинга**.

Он должен отвечать на вопросы:

- кто платит;
- за что платит;
- что уже оплачено;
- что в ожидании;
- что отклонено;
- что дало продление;
- как это влияет на доступ и продукты;
- какие деньги приносит каждый модуль Amonora.

---

## 9.2. Основные секции

### A — Incoming Payments
- pending queue
- confirmed today
- rejected today
- manual review needed
- payment method mix

### B — Revenue
- revenue 7d / 30d
- MRR
- revenue by product
- revenue by plan
- revenue by method
- repeat payments
- refunds / cancellations (в будущем)

### C — Payment Records Table
Поля:
- record_id
- user
- product
- plan
- amount
- method
- status
- created_at
- confirmed_at
- handled_by
- linked subscription
- linked finance entry

### D — Finance Ledger
- доход
- расход
- чистый результат
- notes
- approval state

---

## 9.3. Действия по платежам

- confirm payment
- reject payment with reason
- delete record (строго ограниченно)
- create manual payment
- create finance entry
- attach note
- regenerate entitlement
- open user context

---

## 9.4. Важное правило UX

Подтверждение платежа должно явно показывать:

- какой продукт оплачивается;
- какой тариф активируется;
- на сколько продлевается;
- какая entitlement будет создана/обновлена;
- до какой даты будет активен доступ.

---

## 9.5. Мультипродуктовый биллинг

Панель должна изначально мыслить платежи не только как “VPN-оплата”.

Нужно поддержать модель:

- Access plan
- Automation package
- Data subscription
- AI quota / bundle

Даже если сейчас из этого реально активен только Access, UI и backend-модель должны быть готовы к расширению.

---

# 10. SUPPORT — ОПЕРАТОРСКОЕ ПРОСТРАНСТВО

---

## 10.1. Назначение

Support должен стать **рабочим пространством для решения проблем пользователей**, а не просто отображением переписки.

---

## 10.2. Основные блоки

### Queue
- new
- in_progress
- mine
- closed
- escalated
- by product
- by issue type

### Conversation View
- сообщения
- attachments / media (когда появится)
- linked user
- linked payments
- linked node
- linked access profile
- recent actions
- notes

### Context Sidebar
- user summary
- entitlements
- devices
- last payment
- node / protocol
- similar recent incidents
- known issue banner

---

## 10.3. Категории тикетов

Панель должна поддерживать категории:

- access_issue
- payment_issue
- device_issue
- onboarding_issue
- node_issue
- automation_issue
- data_issue
- ai_issue
- general

---

## 10.4. Действия в support

- assign to self
- transfer
- reply
- close
- reopen
- categorize
- attach incident
- attach payment issue
- attach known issue
- leave internal note

---

## 10.5. Почему support критичен для экосистемы

Когда появятся другие продукты Amonora, support должен быть общим.

Пользователь не будет думать:
- “это access тикет”
- “это AI тикет”
- “это automation тикет”

Он просто пишет.

Значит, support-система должна уметь:
- понять продукт;
- показать контекст;
- направить к правильному модулю;
- учитывать entitlements и usage.

---

# 11. ALERTS / INCIDENTS — ОПЕРАЦИОННЫЙ НЕРВ ЦЕНТРА

---

## 11.1. Отдельный раздел Alerts обязателен

Алерты нельзя прятать только в виджет, drawer или header.

Нужен полноценный раздел.

---

## 11.2. Типы алертов

### System alerts
- backend down
- DB issue
- dashboard issue
- bot issue
- tunnel issue

### Access alerts
- node degraded
- throughput anomaly
- too many support complaints
- profile failure spike
- issuance errors

### Billing alerts
- payment confirmation backlog
- finance mismatch
- payment failure burst

### Product alerts
- automation flow failure
- parser failure
- AI quota exceeded
- AI provider issue

---

## 11.3. Severity model

- Critical
- Warning
- Info

Каждый alert должен иметь:
- timestamp
- affected component
- severity
- short summary
- detailed reason
- suggested action
- link to related entity
- ack / resolved state
- who acknowledged it

---

## 11.4. Incidents

Отдельная сущность от alerts.

Incident должен показывать:
- title
- severity
- started_at
- resolved_at
- impacted products
- impacted nodes/users
- owner
- notes
- root cause
- resolution summary

---

# 12. PRODUCTS — ЦЕНТР УПРАВЛЕНИЯ ПРОДУКТАМИ ЭКОСИСТЕМЫ

---

## 12.1. Зачем нужен раздел Products

Когда у Amonora появятся не только VPN, но и automation/data/AI, нужен единый реестр продуктов.

---

## 12.2. Что показывает раздел Products

Для каждого продукта:

- product_code
- name
- category
- active/inactive
- public/private/beta
- available plans
- active users
- revenue
- support volume
- owner / responsible
- linked modules

Примеры:
- Access VPN
- Access DNS
- Automation Lead Bot Setup
- Automation AI AutoReply
- Data Price Monitor
- AI Support Assistant

---

## 12.3. Действия

- enable product
- hide product
- mark beta
- assign plan
- change public description
- attach knowledge articles
- attach onboarding flow

---

# 13. AUTOMATIONS — УПРАВЛЕНИЕ АВТОМАТИЗАЦИЯМИ

---

## 13.1. Назначение

Раздел должен управлять automation-направлением Amonora.

---

## 13.2. Что показывать

### Projects / Clients
- automation customers
- active projects
- setup status
- maintenance status
- revenue
- linked user/company

### Flows
- flow name
- flow type
- trigger
- integrations
- last run
- success rate
- owner
- enabled/disabled

### Runs
- recent runs
- failed runs
- delayed runs
- retry state

### Integrations
- Telegram
- Google Sheets
- CRM
- Webhooks
- Email
- OpenAI / AI provider
- custom connectors

---

## 13.3. Действия

- create flow
- enable/disable flow
- rerun failed flow
- inspect payload
- edit config
- rotate API key
- open client project
- attach documentation

---

## 13.4. Почему это важно уже сейчас

Даже если ты пока продаёшь automation вручную, панель должна уметь в будущем:
- хранить automation entities;
- показывать активные проекты;
- считать revenue по automation;
- показывать failures и support context.

---

# 14. DATA — УПРАВЛЕНИЕ ПАРСИНГОМ И МОНИТОРИНГОМ

---

## 14.1. Назначение

Раздел Data — это центр управления data-продуктами:

- parsing
- monitoring
- scheduled checks
- data alerts
- source inventory

---

## 14.2. Что показывать

### Sources
- source_id
- type
- domain
- purpose
- owner
- status
- schedule
- last success
- next run

### Jobs
- parsing jobs
- monitoring jobs
- failures
- retries
- output counts

### Results
- latest data
- change detection
- delivered alerts
- customer-facing reports

### Limits / Health
- source stability
- ban risk
- anti-bot issues
- data freshness

---

## 14.3. Действия

- create source
- pause source
- resume source
- run now
- change schedule
- open results
- attach to customer/project
- raise alert

---

# 15. AI — УПРАВЛЕНИЕ AI-ФУНКЦИЯМИ

---

## 15.1. Назначение

AI section должен быть центром управления AI-модулем Amonora.

---

## 15.2. Что показывать

### AI Products / Use Cases
- support assistant
- content generator
- classifier
- summarizer
- automation AI blocks

### Requests
- count
- failures
- latency
- usage by product
- usage by customer

### Quotas
- token budget / request budget
- remaining quota
- overages
- billing impact

### Templates / Prompts
- template name
- use case
- version
- status
- owner

---

## 15.3. Действия

- enable use case
- disable use case
- change quota
- rotate provider key
- inspect failed AI request
- test template
- attach to product flow

---

# 16. KNOWLEDGE — БАЗА ЗНАНИЙ И RUNBOOKS

---

## 16.1. Назначение

Knowledge должен быть **операционной базой знаний всей экосистемы**.

---

## 16.2. Что должно храниться

- product docs
- architecture docs
- rollback docs
- incident runbooks
- onboarding docs
- support scripts
- payment rules
- node maintenance docs
- automation templates
- AI prompt docs
- Data source notes

---

## 16.3. Что должен уметь раздел

- list documents
- search
- open rendered markdown
- show source mode
- show last sync
- mark outdated
- generate report
- attach docs to entities:
  - node
  - product
  - flow
  - incident
  - alert
  - support issue

---

# 17. SETTINGS — САМАЯ ОПАСНАЯ И САМАЯ МОЩНАЯ ЗОНА

---

## 17.1. Общий принцип

Settings нельзя держать как “мешок всего подряд”.

Нужно делить на подзоны.

---

## 17.2. Product Settings
- тарифы
- trial rules
- device limits
- region availability
- default protocols
- default product visibility
- feature flags

---

## 17.3. Infra Settings
- health thresholds
- node role defaults
- maintenance mode rules
- service inventory
- tunnel settings metadata
- alerting thresholds

---

## 17.4. Billing Settings
- payment methods visibility
- confirmation rules
- finance categories
- refund rules
- invoice settings (в будущем)

---

## 17.5. Environment / Secrets
- masked env values
- change history
- diff preview
- confirm modal
- audit log
- change reason required

---

## 17.6. Service Controls
- start/status/restart
- logs preview
- last restart
- responsible role
- risky action label

И обязательно должен учитываться **реальный prod-inventory**, а не исторический список “трёх сервисов”.

---

# 18. AUDIT — ЖУРНАЛ ДЕЙСТВИЙ

---

## 18.1. Обязательный раздел

Audit должен быть отдельным полноценным экраном.

---

## 18.2. Что записывать

- admin login
- session revoke
- user access actions
- device creation / deletion
- payment confirm / reject
- support actions
- settings changes
- env changes
- service restarts
- node status changes
- automation config changes
- data source changes
- AI config changes

---

## 18.3. Что показывать

- who
- when
- action
- entity
- before/after summary
- result
- risk level
- notes

---

# 19. РОЛИ И ДОСТУПЫ

---

## 19.1. Owner
Доступ:
- всё
- env
- service control
- destructive actions
- billing
- audit
- products
- entitlements
- feature flags

---

## 19.2. Tech Admin
Доступ:
- users
- access
- nodes
- support
- часть settings
- alerts
- knowledge
- limited payments actions

Без:
- самых опасных env / destructive billing / owner-only deletes

---

## 19.3. Support
Доступ:
- support
- users read / limited actions
- payments read / limited workflow
- access limited troubleshooting
- knowledge

Без:
- infra mutate
- env
- service restart
- destructive user actions
- sensitive billing operations

---

## 19.4. Product / Operations role (в будущем)
Для роста экосистемы полезно предусмотреть:
- product ops
- finance ops
- automation ops
- data ops

---

# 20. ОБЯЗАТЕЛЬНАЯ UX-МОДЕЛЬ ДЛЯ ДЕЙСТВИЙ

---

## 20.1. Любое действие должно иметь 6 состояний

1. available  
2. disabled-with-reason  
3. confirm  
4. pending  
5. success  
6. failed-with-reason  

---

## 20.2. Для опасных действий обязательно

- reason input
- explicit confirm
- impact note
- audit record
- result

---

## 20.3. Для страниц обязательно

- loading state
- empty state
- error state
- manual refresh
- last updated
- permission-aware rendering

---

# 21. КАК ПАНЕЛЬ ДОЛЖНА УЧИТЫВАТЬ ДРУГИЕ ПРОДУКТЫ И ПРОЕКТЫ

Это критично для Amonora как экосистемы.

---

## 21.1. Панель не должна быть “VPN-only”

Даже если сейчас основной прод — VPN, структура должна учитывать, что в Amonora будут:

- Access
- Automations
- Data
- AI
- будущие SaaS / инструменты

---

## 21.2. Для этого нужны общие сущности

### User
Один пользователь может иметь:
- VPN plan
- Automation service package
- Data monitor subscription
- AI quota

### Product
Каждый продукт имеет:
- code
- type
- plans
- entitlements
- support category
- revenue stream

### Subscription / Entitlement
Одна entitlement-модель должна поддерживать:
- product_code
- plan_code
- status
- limits
- expires_at
- metadata

### Support
Support должен понимать product category.

### Billing
Billing должен быть мультипродуктовым.

### Dashboard
Dashboard должен показывать business/product split.

---

## 21.3. Как это отразить в интерфейсе

- фильтры по продуктам почти везде;
- revenue by product;
- support by product;
- alerts by product;
- entitlements by product;
- user 360 с product tabs.

---

# 22. КАК ПАНЕЛЬ ДОЛЖНА РАСТИ ПО ЭТАПАМ

---

## Stage 1 — Hardened VPN Control Center
Что обязательно:
- Dashboard
- Users
- Access
- Nodes
- Payments
- Support
- Alerts
- Settings
- Knowledge
- Audit

---

## Stage 2 — Multi-Product Ready
Добавить:
- Products
- product entitlements
- product filters
- revenue by product
- support by product

---

## Stage 3 — Automation / Data / AI integration
Добавить:
- Automations section
- Data section
- AI section
- background jobs observability
- usage and quota tracking

---

## Stage 4 — Full Ecosystem Control Plane
Итог:
- единый core
- единый billing
- единый support
- единый audit
- мультипродуктовая панель
- зрелый operational center

---

# 23. ЧТО ДОЛЖНО БЫТЬ НА ВИДУ ВСЕГДА

В любом состоянии панели, особенно в desktop layout, должны быть быстро доступны:

- global search
- current health summary
- notifications / alerts
- active role
- environment / prod badge
- session status
- profile menu
- quick actions
- last refresh / last sync

---

# 24. БЫСТРЫЕ QUICK ACTIONS, КОТОРЫЕ НУЖНЫ В ПАНЕЛИ

Примеры:

- найти пользователя
- создать ручной платёж
- открыть pending payments
- открыть new tickets
- refresh nodes
- create device
- open incidents
- open knowledge
- run support report
- create automation lead note (в будущем)

---

# 25. КЛЮЧЕВАЯ ЦЕЛЕВАЯ КАРТА ПАНЕЛИ

Итоговая карта Amonora Control Center:

### Overview
- состояние системы
- KPI
- requires attention
- revenue
- activity

### Users
- список
- User 360
- устройства
- support / payments context

### Access
- profiles
- issuance
- devices
- analytics
- overrides

### Nodes
- health
- metrics
- roles
- actions
- history

### Payments
- pending
- confirmed
- rejected
- finance
- product billing

### Support
- queue
- conversations
- context
- categorization

### Products
- реестр продуктов
- plans
- revenue
- owners

### Automations
- projects
- flows
- runs
- failures
- integrations

### Data
- sources
- jobs
- alerts
- results

### AI
- use cases
- requests
- quota
- templates

### Alerts
- alerts
- incidents
- severity
- status

### Knowledge
- docs
- runbooks
- reports
- generated notes

### Settings
- product
- infra
- billing
- env
- service controls

### Audit
- всё важное, что делали админы

---

# 26. ФИНАЛЬНАЯ ПРОДУКТОВАЯ ФОРМУЛА

Amonora Control Center должен быть:

- **операционным** — чтобы держать систему живой;
- **продуктовым** — чтобы управлять пользователями, подписками и продуктами;
- **экосистемным** — чтобы поддерживать VPN, automation, data и AI;
- **безопасным** — чтобы не убивать прод одним неосторожным действием;
- **role-aware** — чтобы каждый видел свой уровень;
- **масштабируемым** — чтобы не пришлось строить новую панель при добавлении новых продуктов.

---

# 27. ГЛАВНАЯ МЫСЛЬ

> Amonora Control Center — это не просто админка.
> Это **центр управления экосистемой Amonora**:
>
> единое ядро  
> + управление доступом  
> + управление пользователями  
> + управление деньгами  
> + управление поддержкой  
> + управление инфраструктурой  
> + управление новыми продуктами  
> + наблюдаемость  
> + безопасность  
> + audit

---

# END
