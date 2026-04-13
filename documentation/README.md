# Amonora Documentation

Это центральная папка документации проекта `Amonora`.

## С чего начинать
Главная точка входа теперь:

- `INDEX.md`

Если нужен канонический срез текущего состояния, читать сначала:

- `PROJECT_OVERVIEW.md`
- `ARCHITECTURE.md`
- `DOMAIN.md`
- `REPO_RULES.md`
- `RUNBOOK.md`
- `FEATURES.md`
- `ALERTS_ATTENTION_MAP.md` — если нужно быстро понять, какие user-level и system-level состояния уже требуют внимания и где они сейчас видны
- `REPAIR_REASON_MAP.md` — если нужно быстро понять канонический набор repair reasons, legacy aliases и как payment/access/VPN причины теперь нормализуются
- `MANUAL_PAYMENTS_FLOW_MAP.md` — если нужно быстро понять реальный lifecycle ручных оплат, где в нём сидит оператор и где manual payment превращается в access/repair работу
- `PAYMENT_SUPPORT_ACCESS_TRIAGE_MAP.md` — если нужно понять, где payment/support/access всё ещё требуют ручного triage и какие следующие hardening-задачи дают лучший эффект
- `SUPPORT_BACKLOG_REPAIR_WORKLOAD_MAP.md` — если нужно понять, откуда реально растёт support load вокруг access/payment/repair и какие маленькие улучшения сильнее всего снизят ручную нагрузку
- `HISTORICAL_SUPPORTING_MAP.md` — если нужно понять, какие supporting и historical docs ещё полезны, но уже не являются каноном

## Как теперь устроена документация

### Канон текущего проекта

- `PROJECT_OVERVIEW.md`
- `ARCHITECTURE.md`
- `DOMAIN.md`
- `REPO_RULES.md`
- `RUNBOOK.md`
- `FEATURES.md`
- `ALERTS_ATTENTION_MAP.md`
- `REPAIR_REASON_MAP.md`
- `MANUAL_PAYMENTS_FLOW_MAP.md`
- `PAYMENT_SUPPORT_ACCESS_TRIAGE_MAP.md`
- `SUPPORT_BACKLOG_REPAIR_WORKLOAD_MAP.md`
- `TEAM_CONTEXT.md`
- `PUBLIC_SURFACES.md`

### Ops и runtime

- `ops/`
- `vpn/`

### Product / strategy

- `product/`
- `strategy/`

### Business layer

- `business/`

### AI layer

- `ai/`

### Archive

- `archive/`

### Historical / supporting map

- `HISTORICAL_SUPPORTING_MAP.md`

## Что ещё лежит в корне documentation

В корне также могут оставаться только канон, навигация и legal/policy документы. Supporting и historical материалы теперь вынесены в отдельные слои:

- `supporting/product.md`
- `supporting/bot-flow.md`
- `supporting/dashboard.md`
- `supporting/panel-ui-deep-dive.md`
- `supporting/deployment.md`
- `supporting/infrastructure.md`
- `supporting/support-bot.md`
- `supporting/user-guide.md`
- `archive/snapshots/*.md`
- юридические документы

Их не нужно путать с каноническим набором `PROJECT_OVERVIEW / ARCHITECTURE / DOMAIN / REPO_RULES / RUNBOOK / FEATURES`.
Если документ не входит в этот канон и не лежит в одном из слоёв `ops/`, `vpn/`, `product/`, `strategy/`, `business/`, `ai/`, `supporting/`, `archive/`, его стоит воспринимать как вспомогательный или исторический материал, пока не доказано обратное.
Отдельная карта для этого слоя лежит в `HISTORICAL_SUPPORTING_MAP.md`.

Отдельный локальный recovery-док теперь лежит в ops-слое:

- `ops/LOCAL_RESTORE_RECIPE.md` — локальный restore drill для PostgreSQL dump и `x-ui.db` без касания прода, включая one-click PostgreSQL restore drill

## Как используется документация

- эта папка лежит в репозитории и пушится в GitHub
- дашборд `Amonora Control Center` читает её как базу знаний
- основной источник для вкладки `Документация` — GitHub-ветка `develop`
- если GitHub временно недоступен, дашборд показывает локальную копию из проекта

Отдельные runtime- и branch-audit документы теперь тоже лежат здесь, в первую очередь в `ops/`.
Они нужны, чтобы не смешивать канон проекта с эксплуатационными проверками и baseline diff-проходами.

## Подход к обновлению

1. Любое крупное изменение в продукте, серверной схеме, дашборде или support-боте сначала фиксируется здесь.
2. После этого документация уходит в GitHub вместе с кодом.
3. Админы читают уже актуальные материалы прямо из дашборда.

## Базовый принцип

Документация должна описывать реальное состояние проекта:

- без устаревших тарифов и старых серверов
- без секретов и токенов
- с понятным разделением между `backend`, `VPN`, `support` и `dashboard`
- с разделением между каноном, ops, strategy, business и AI-слоем
- с явной пометкой, где документ описывает текущее состояние, а где future vision или historical context
