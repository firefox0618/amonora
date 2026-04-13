# AMONORA — SYSTEM DESIGN (SENIOR LEVEL)

Дата: 19 марта 2026

---

# 🎯 ЦЕЛЬ

> Зафиксировать технический system design для Amonora как экосистемы:
- как это масштабировать
- как разделять компоненты
- как думать про нагрузку
- как строить отказоустойчивость
- как не утонуть в хаосе при росте

---

# 1. ВЫСОКОУРОВНЕВАЯ МОДЕЛЬ

Amonora = платформа из общего ядра и нескольких продуктовых модулей.

## Логическая схема

```text
Clients
  ↓
Telegram / Web / API
  ↓
Amonora Gateway Layer
  ↓
Core Services
  ↓
Product Services
  ↓
Infra / Storage / External Integrations
```

---

# 2. ОСНОВНЫЕ СЛОИ СИСТЕМЫ

## 2.1 Entry Layer
Точка входа пользователей и админов.

### Что сюда входит:
- Telegram Bot
- Support Bot
- Dashboard / Web UI
- Public API (в будущем)

### Задача:
- принять запрос
- аутентифицировать
- направить в нужный сервис

---

## 2.2 Core Layer
Общее ядро всей платформы.

### Что сюда входит:
- User service
- Auth service
- Billing service
- Subscription / Access service
- Notification service
- Support service
- Audit / Event logging

### Задача:
- быть общим фундаментом для всех модулей

---

## 2.3 Product Layer
Отдельные продуктовые модули.

### Модули:
- Access (VPN / DNS / Proxy)
- Automations
- Data
- AI

### Задача:
- реализовать прикладную ценность
- использовать общее ядро
- не дублировать user/auth/billing логику

---

## 2.4 Infra Layer
Техническая инфраструктура.

### Что сюда входит:
- PostgreSQL
- Redis (в будущем)
- Background workers
- Cron / scheduler
- Object storage (в будущем)
- Monitoring / logs
- Nginx / reverse proxy
- VPN nodes
- External providers / APIs

---

# 3. ПРИНЦИПЫ АРХИТЕКТУРЫ

## Принцип 1
> Один Core — много продуктов

Нельзя делать отдельную авторизацию, отдельный биллинг и отдельную базу пользователей под каждый продукт.

---

## Принцип 2
> Control plane отдельно от data plane

### Control plane:
- бот
- backend
- dashboard
- billing
- support
- управление доступом

### Data plane:
- VPN ноды
- парсеры
- AI-job execution
- automation jobs

Это критично для масштаба.

---

## Принцип 3
> Сначала modular monolith, потом service extraction

Тебе сейчас не нужны “микросервисы ради микросервисов”.

Правильный путь:
1. единый backend с чистыми модулями
2. выделение тяжёлых частей позже

---

## Принцип 4
> Async всё, что может быть долгим

Долгие операции нельзя держать в user-facing request flow.

Примеры:
- парсинг
- AI generation
- массовые нотификации
- health-check нод
- sync с внешними панелями
- построение отчётов

---

# 4. КАК ДУМАТЬ О НАГРУЗКЕ

Нагрузка у Amonora будет не одной природы.

## Тип 1 — Interactive load
Быстрые действия пользователей:
- открыть dashboard
- нажать кнопку в боте
- получить ключ
- оплатить
- запросить статус

Требование:
- низкая задержка
- стабильные API

---

## Тип 2 — Background load
Фоновые задачи:
- watchdog
- sync с 3x-ui
- проверка платежей
- отправка уведомлений
- чистка старых данных
- support retention

Требование:
- не мешать interactive load

---

## Тип 3 — Heavy job load
Тяжёлые задачи:
- парсинг
- AI ответы
- генерация отчётов
- массовая обработка событий

Требование:
- отдельные workers / очереди

---

# 5. РЕКОМЕНДУЕМАЯ АРХИТЕКТУРА НА ТВОЁМ ЭТАПЕ

## Stage A — ранний прод
Сейчас правильная архитектура:

```text
Nginx
  ↓
Backend monolith
  ├── Bot logic
  ├── Dashboard API
  ├── Billing
  ├── Support
  ├── Access module
  ├── Automation module (позже)
  └── AI/Data module (позже)
  ↓
PostgreSQL
```

Параллельно:
- VPN nodes
- 3x-ui control plane
- scheduler / watchdog

---

## Почему это нормально:
- меньше хаоса
- проще деплой
- меньше точек отказа
- быстрее менять продукт

---

# 6. КОГДА НУЖНЫ ОЧЕРЕДИ

Очереди нужны, когда:
- задача не должна блокировать ответ пользователю
- задача может падать и повторяться
- задача тяжёлая
- задача массовая

## Для Amonora это:
- отправка нотификаций
- парсинг сайтов
- AI обработка запросов
- синхронизация с внешними API
- health polling
- биллинговые фоновые проверки

---

## Что использовать как этапы зрелости

### Сейчас
- cron + async tasks + аккуратный scheduler

### Следующий уровень
- Redis + task queue

### Дальше
- отдельные worker processes

---

# 7. КАК ДУМАТЬ ПРО БАЗУ ДАННЫХ

## PostgreSQL — центральное хранилище
Подходит как source of truth для:
- users
- subscriptions
- vpn_clients
- devices
- payments
- support tickets
- admin sessions
- audit events
- product entitlements

---

## Что важно:
- не делать хаотичные связи
- не смешивать бизнес-сущности и тех. мусор
- иметь явные статусы
- иметь created_at / updated_at / source / metadata

---

## Желательные таблицы / домены

### Identity
- users
- admins
- sessions
- auth_codes

### Billing
- plans
- subscriptions
- payment_records
- invoices (позже)

### Access
- vpn_clients
- devices
- regions
- node_assignments

### Support
- tickets
- ticket_messages
- support_events

### Platform
- notifications
- audit_log
- feature_flags
- system_events

### Future products
- automation_flows
- automation_runs
- data_sources
- data_results
- ai_requests
- ai_outputs

---

# 8. ГДЕ НУЖЕН REDIS

Redis нужен не “потому что модно”, а по конкретным задачам.

## Подходит для:
- кэша dashboard агрегатов
- rate limit
- очередей
- временных сессий
- idempotency keys
- быстрых counters
- distributed locks (в будущем)

---

## Пока без него можно жить, если:
- трафик маленький
- нет тяжёлых burst-нагрузок
- нет сложного async processing

---

# 9. BACKEND DESIGN

## Текущий правильный путь
Один backend, но разделённый на доменные модули.

### Пример структуры:
- `core/`
- `auth/`
- `billing/`
- `support/`
- `access/`
- `automation/`
- `data/`
- `ai/`
- `ops/`
- `integrations/`

---

## Почему это важно
Чтобы потом можно было:
- выделять части в отдельные сервисы
- не переписывать всё заново
- понимать ownership кода

---

# 10. API DESIGN

## Принципы
- единая версия API
- явные домены
- идемпотентность там, где важны деньги и доступ
- понятные статусы

---

## Пример API пространства

### Auth
- `POST /api/v2/auth/request-code`
- `POST /api/v2/auth/verify`

### Users
- `GET /api/v2/users`
- `GET /api/v2/users/{id}`

### Access
- `POST /api/v2/access/devices`
- `DELETE /api/v2/access/devices/{id}`
- `POST /api/v2/access/extend`
- `GET /api/v2/access/config/{device_id}`

### Billing
- `GET /api/v2/payments`
- `POST /api/v2/payments/create`
- `POST /api/v2/payments/confirm`

### Support
- `GET /api/v2/support/tickets`
- `POST /api/v2/support/tickets/{id}/reply`

### Automation
- `POST /api/v2/automation/flows`
- `POST /api/v2/automation/run`

### Data
- `POST /api/v2/data/sources`
- `GET /api/v2/data/results`

### AI
- `POST /api/v2/ai/chat`
- `POST /api/v2/ai/generate`

---

# 11. EVENT-DRIVEN МЫШЛЕНИЕ

Даже без полноценной event bus архитектуры полезно мыслить событиями.

## Примеры событий:
- user_created
- device_created
- payment_confirmed
- subscription_extended
- node_degraded
- support_ticket_opened
- automation_run_started
- automation_run_finished
- data_alert_triggered

---

## Зачем это нужно:
- логирование
- уведомления
- аналитика
- будущая автоматизация
- меньше жёстких связей в коде

---

# 12. ОТКАЗОУСТОЙЧИВОСТЬ

## 12.1 Главные точки отказа сейчас
- backend single point of failure
- PostgreSQL на одном сервере
- ручной deploy риск
- 1 основная VPN-нода
- отсутствие зрелой очереди задач

---

## 12.2 Что делать поэтапно

### Сейчас
- backup strategy
- rollback kit
- deployment discipline
- мониторинг ключевых сервисов
- health checks

### Следующий уровень
- standby backup backend
- backup DB snapshots
- отдельные worker processes
- graceful degradation

### Дальше
- failover core
- replicated DB
- queue-backed processing
- multi-node routing logic

---

## 12.3 Graceful degradation
Система должна не “умирать целиком”, а деградировать частями.

### Примеры:
- если AI модуль упал → VPN и billing всё равно работают
- если Data scraping недоступен → бот и support продолжают жить
- если Estonia умерла → Germany и core продолжают работать
- если support-notifications сломались → доступ пользователей не ломается

---

# 13. SECURITY DESIGN

## Основные правила:
- панели не открывать наружу без причины
- секреты не хранить в коде
- разделять prod/test env
- ограничивать admin actions
- логировать критичные изменения
- ставить rate limits на auth и чувствительные endpoints

---

## Критичные зоны:
- billing
- user access
- admin auth
- VPN config generation
- SSH tunnels / infra integrations

---

# 14. OBSERVABILITY

Тебе нужна не просто “работает/не работает”, а наблюдаемость.

## 4 уровня наблюдаемости:

### 1. Health
- сервис жив / мёртв

### 2. Metrics
- latency
- error rate
- CPU / RAM
- active users
- payments
- node health

### 3. Logs
- ошибки backend
- ошибки auth
- support actions
- billing actions
- sync actions

### 4. Events
- user actions
- payment events
- access events
- admin actions

---

# 15. MONITORING DESIGN

## Что мониторить в первую очередь

### Core
- backend process
- dashboard process
- nginx
- postgres
- disk usage
- memory pressure

### VPN
- node availability
- active clients
- packet loss / latency proxy indicators
- health check consistency

### Product
- successful config issuance
- failed config issuance
- payment confirmations
- support ticket volume
- auth failures

---

# 16. DEPLOYMENT DESIGN

## Сейчас
Самый правильный путь:
- один репозиторий
- понятные модули
- ручной деплой по чеклисту
- backup before deploy
- changelog
- smoke test after deploy

---

## Позже
Когда вырастешь:
- build artifacts
- staged deploy
- environment-specific configs
- worker restart isolation
- canary logic для рискованных изменений

---

# 17. КАК ВЫДЕЛЯТЬ СЕРВИСЫ ПОТОМ

Сначала не надо дробить всё.

Выделять надо только то, что реально болит.

## Порядок вероятного выделения:

### 1. Workers / background jobs
Первое, что обычно стоит вынести.

### 2. Automation execution
Если появится много n8n/flow logic.

### 3. Data scraping engine
Если парсинг станет тяжёлым.

### 4. AI execution service
Если будет много генерации и inference tasks.

### 5. Billing adapters
Если появятся разные платёжные каналы.

Core user/auth/billing domain при этом может долго жить в одном приложении.

---

# 18. NODE STRATEGY С ТОЧКИ ЗРЕНИЯ SYSTEM DESIGN

Ноды — это не просто VPS, а исполняющие единицы data plane.

## Типы нод:
- Primary access node
- Fallback access node
- Experimental node
- Scraper node (в будущем)
- Worker node (в будущем)

---

## Нельзя:
- смешивать всё на одной слабой машине
- вешать тяжёлый парсинг на core
- делать AI-heavy задачи на том же сервере, где крутится критичный control plane

---

# 19. MULTI-PRODUCT BILLING DESIGN

Если Amonora — экосистема, биллинг должен мыслиться как entitlement system.

## Не только “оплата VPN”, а:
- какой продукт активен
- какой план активен
- до какого времени
- какие лимиты
- какие feature flags включены

---

## Пример:
User может иметь одновременно:
- VPN plan active
- Automation support package
- Data alerts subscription
- AI quota

То есть нужна модель:
- `subscription`
- `product_code`
- `plan_code`
- `status`
- `expires_at`
- `limits`
- `metadata`

---

# 20. FEATURE FLAGS

Очень полезно заранее мыслить feature flags.

## Что можно флагировать:
- новый VPN inbound profile
- новый payment flow
- новый dashboard section
- доступ к automation module
- beta AI features
- experimental node assignment

---

## Зачем:
- rollout по частям
- безопасное тестирование
- меньше массовых поломок

---

# 21. SUPPORT SYSTEM DESIGN

Support для экосистемы должен быть мультипродуктовым.

## Тикет должен понимать:
- какой продукт
- какой пользователь
- какой регион / нода
- какой тип проблемы
- какой статус
- какие действия уже были

---

## Категории:
- access_issue
- payment_issue
- device_issue
- support_general
- automation_issue
- data_issue
- ai_issue

---

# 22. DOMAIN MODEL МЫШЛЕНИЕ

Полезно мыслить платформу как набор доменов.

## Домены:
- Identity
- Access
- Billing
- Support
- Automation
- Data
- AI
- Notifications
- Operations

---

## Это помогает:
- строить код без хаоса
- выделять ownership
- изолировать изменения
- масштабировать понятнее

---

# 23. РЕКОМЕНДОВАННАЯ ЭВОЛЮЦИЯ

## Phase 1 — Stabilized Monolith
Сейчас:
- один backend
- модульная архитектура
- Postgres
- ручной deploy
- watchdog
- live users

## Phase 2 — Monolith + Workers
Добавляется:
- отдельный worker process
- очереди / Redis
- async heavy tasks
- data/AI background jobs

## Phase 3 — Platform Extraction
Выделяются:
- scraping engine
- AI job service
- automation executor

## Phase 4 — Resilient Platform
Добавляется:
- standby core
- stronger DB strategy
- service isolation
- routing by health
- staged release logic

---

# 24. ЧТО ТЕБЕ НЕ НУЖНО ПРЯМО СЕЙЧАС

❌ Kubernetes  
❌ microservices everywhere  
❌ service mesh  
❌ 10 баз данных  
❌ event bus ради моды  
❌ сверхсложный CI/CD  

---

# 25. ЧТО ТЕБЕ НУЖНО ПРЯМО СЕЙЧАС

✔ чистый modular backend  
✔ backup / rollback  
✔ documented flows  
✔ clear domain separation  
✔ safe deploy discipline  
✔ VPN stabilization  
✔ readiness for workers later  

---

# 26. ПРАКТИЧЕСКИЙ DESIGN-ПЛАН ДЛЯ ТЕБЯ

## Шаг 1
Стабилизировать текущий core:
- git cleanup
- deploy discipline
- rollback
- regression

## Шаг 2
Описать домены внутри backend:
- auth
- billing
- access
- support
- notifications
- ops

## Шаг 3
Подготовить место для новых модулей:
- automation
- data
- ai

## Шаг 4
Вынести тяжёлые задачи в background execution модель

## Шаг 5
Когда появится рост:
- Redis
- workers
- refined monitoring
- node role separation

---

# 27. ФИНАЛЬНАЯ АРХИТЕКТУРНАЯ ФОРМУЛА

> Amonora должен расти не как набор случайных функций, а как платформа:
>
> **единое ядро + модульные продукты + отдельный data plane + поэтапная эволюция в сторону отказоустойчивости.**

---

# 28. ГЛАВНАЯ МЫСЛЬ

> Не строй “большую архитектуру”.
> Строй архитектуру, которая может вырасти без переписывания всего проекта.

---

# END
