# Дашборды Grafana

> ⚠️ **УДАЛЕНО:** Grafana была полностью удалена с сервера Эстонии. Сервер теперь содержит только VPN-ноду. Этот документ сохранён как историческая справка.

## Обзор

Grafana — внутренняя аналитическая панель Amonora, работавшая на сервере Эстонии.

## URL и доступ

| Параметр | Значение |
|----------|----------|
| **URL** | `https://grafana.amonoraconnect.com/` |
| **Аутентификация** | Basic Auth (nginx `.htpasswd-grafana`) + логин/пароль Grafana |
| **Внутренний порт** | `127.0.0.1:3002` |
| **Протокол** | HTTP (TLS terminates на nginx) |
| **Тема** | Dark (по умолчанию) |
| **Автообновление** | Каждые 5 минут |

## Подключение к данным

Grafana подключается к PostgreSQL core-сервера через SSH-туннель:

```
Grafana (Эстония) → SSH-tunnel (127.0.0.1:15432) → PostgreSQL (46.21.81.186:5432)
```

**Конфигурация туннеля** (`/etc/amonora/grafana-db-tunnel.env`):

| Переменная | Значение |
|-----------|----------|
| `GRAFANA_ANALYTICS_TUNNEL_BIND_HOST` | `127.0.0.1` |
| `GRAFANA_ANALYTICS_TUNNEL_LOCAL_PORT` | `15432` |
| `GRAFANA_ANALYTICS_TUNNEL_CORE_HOST` | `46.21.81.186` |
| `GRAFANA_ANALYTICS_TUNNEL_CORE_PORT` | `22` |
| `GRAFANA_ANALYTICS_TUNNEL_CORE_USER` | `root` |

**Конфигурация БД** (`/etc/amonora/grafana.env`):

| Переменная | Значение |
|-----------|----------|
| `GRAFANA_ANALYTICS_DB_HOST` | `127.0.0.1` |
| `GRAFANA_ANALYTICS_DB_PORT` | `15432` |
| `GRAFANA_ANALYTICS_DB_NAME` | `amonora` |
| `GRAFANA_ANALYTICS_DB_USER` | `amonora_grafana_reader` |
| `GRAFANA_ANALYTICS_DB_SSLMODE` | `disable` |

### Источник данных в Grafana

- **Тип**: PostgreSQL
- **UID**: `amonora-analytics`
- **User**: `amonora_grafana_reader` (read-only, шаблон гранта в `ops/grafana/sql/grant_grafana_reader.sql.template`)

## Дашборды

В системе 8 дашбордов, генерируемых через `ops/grafana/build_suite.py`:

### 1. Главная Amonora (`amonora-home`)

**UID**: `amonora-home` | **Теги**: `analytics, home, owner, stage-b`

Основной executive-срез. Показывает:

- **Ключевые показатели**: переходы по ссылке, старты в боте, подтверждения подписки, выданные ключи, успешные оплаты, первые подключения, продления, выручка (₽)
- **Конверсии**: в оплату (%), в подключение (%), разрыв оплата → подключение
- **Активные подписки**: текущее количество
- **Короткая воронка**: 10 этапов от link_touched до subscription_renewed
- **Окна**: Сегодня / 7д / 30д — сравнительная таблица
- **Контроль**: целостность атрибуции, свежесть данных, активные алерты

**Переменные**:
- `source_mode` — атрибуция (Первый источник / Последний источник)
- `source_key` — фильтр по источнику/start_param

### 2. Воронка роста (`amonora-growth-funnel`)

**UID**: `amonora-growth-funnel` | **Теги**: `analytics, growth, stage-b`

Детальная воронка роста с разбивкой по этапам:
- Переходы → Старты → Подписки → Ключ → Оплата → Подключение → Продление
- Конверсии между этапами
- Динамика по дням (timeseries)

### 3. Источники и посты (`amonora-source-performance`)

**UID**: `amonora-source-performance` | **Теги**: `analytics, sources`

Анализ эффективности источников трафика:
- Сравнение по source_key (реферальные ссылки, посты, реклама)
- Конверсия от источника до оплаты
- Выручка по источникам

### 4. Выручка и монетизация (`amonora-revenue-monetization`)

**UID**: `amonora-revenue-monetization` | **Теги**: `analytics, revenue`

Финансовые показатели:
- Общая выручка (new + renewal)
- Выручка по тарифам (1м, 3м, 6м, 12м)
- Динамика платежей
- Средний чек

### 5. Удержание и отток (`amonora-retention-churn`)

**UID**: `amonora-retention-churn` | **Теги**: `analytics, retention`

- Коэффициент удержания по когортам
- Отток пользователей
- Сравнение когорт: trial_started vs subscription_activated

### 6. Качество подключения (`amonora-connection-quality`)

**UID**: `amonora-connection-quality` | **Теги**: `analytics, connection`

Технические метрики подключений:
- Успешность подключений
- Время подключения
- Ошибки provisioning

### 7. Операции и ремонты (`amonora-ops-repair`)

**UID**: `amonora-ops-repair` | **Теги**: `analytics, ops, repair`

Операционные метрики:
- Открытые ремонты (vpn_repair_needed)
- Успешность авто-восстановления
- Время ремонта

### 8. Алерты и инциденты (`amonora-alerts-incidents`)

**UID**: `amonora-alerts-incidents` | **Теги**: `analytics, alerts`

- Активные инциденты по категориям (nodes, services, users)
- История инцидентов
- Время восстановления
- Частота алертов

## Навигация между дашбордами

Все дашборды связаны навигационными ссылками (кнопка сверху):

```
Главная → Воронка роста → Источники → Выручка → Удержание → Качество → Операции → Алерты
```

Каждая ссылка сохраняет текущие параметры `source_mode`, `source_key`, `cohort_type` и временной диапазон.

## Как подключиться

### 1. Через браузер (внешний доступ)

```
https://grafana.amonoraconnect.com/
```

Введи учётные данные Basic Auth (nginx), затем логин/пароль Grafana.

### 2. Через SSH-туннель (локальный доступ)

Если Grafana недоступна напрямую, создай туннель:

```bash
ssh -N -L 3002:127.0.0.1:3002 root@<estonia-host>
```

Затем открой `http://localhost:3002` в браузере.

### 3. Проверка туннеля к БД

```bash
# На сервере Эстонии
systemctl status amonora-grafana-db-tunnel

# Проверка подключения к БД
psql -h 127.0.0.1 -p 15432 -U amonora_grafana_reader -d amonora -c "SELECT 1"
```

## SQL-источники данных

Дашборды работают с таблицами PostgreSQL:

| Таблица | Назначение |
|---------|-----------|
| `analytics_daily_stage_counts` | Ежедневные срезы воронки (по этапам и источникам) |
| `analytics_daily_revenue` | Ежедневная выручка (по источникам и типам платежей) |
| `analytics_hourly_ops_snapshots` | Ежечасные снимки операционных метрик |
| `analytics_runtime_status` | Текущий статус runtime-показателей |
| `analytics_events` | Ledger событий для full-refresh |

### Пример SQL-запроса (стат-панель)

```sql
SELECT COALESCE(SUM(users_count), 0)::bigint AS value
FROM analytics_daily_stage_counts
WHERE $__timeFilter(bucket_date::timestamp)
  AND source_mode = '${source_mode}'
  AND ('${source_key}' = '__all' OR source_key = '${source_key}')
  AND event_name = 'bot_start';
```

## Администрирование

```bash
# Перезапуск Grafana
systemctl restart amonora-grafana

# Проверка лога
journalctl -u amonora-grafana -n 50 --no-pager

# Перезапуск туннеля к БД
systemctl restart amonora-grafana-db-tunnel

# Проверка конфигурации
cat /opt/amonora_bot/ops/grafana/grafana.ini
```

### Ресурсы

- `MemoryMax=512M`
- `CPUQuota=30%`
- `PrivateTmp=true`
- `ProtectSystem=full`
