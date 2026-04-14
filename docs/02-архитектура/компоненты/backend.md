# Backend — ядро системы

## Подключение к PostgreSQL

Файл: `backend/core/database.py`

```python
engine = create_async_engine(
    config.database_url,  # postgresql+asyncpg://user:pass@host:port/dbname
    echo=False,
)
async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
Base = declarative_base()
```

URL формируется из `bot.config`:
```
postgresql+asyncpg://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}
```

Конфигурация берётся из env-переменных: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS`.

## Модели данных

### User (`users`)

Основная модель пользователя.

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | int | PK |
| `telegram_id` | BigInteger, unique | Telegram ID пользователя |
| `username` | String(255) | Username из Telegram |
| `is_synthetic` | Boolean | Флаг синтетического пользователя (test, bridge, smoke) |
| `preferred_mode` | String(20) | "stable" по умолчанию |
| `preferred_protocol` | String(50) | "vless" по умолчанию |
| `trial_used` | Boolean | Был ли trial использован |
| `trial_started_at` | DateTime | Начало trial |
| `trial_expires_at` | DateTime | Окончание trial |
| `trial_channel_unsubscribed_at` | DateTime | Когда отписался от канала |
| `trial_activity_level` | String(20) | "low" по умолчанию |
| `trial_engaged_at` | DateTime | Техническая активность в trial |
| `subscription_started_at` | DateTime | Начало платной подписки |
| `subscription_expires_at` | DateTime | Окончание подписки |
| `subscription_status` | String(50) | "inactive" по умолчанию |
| `subscription_source` | String(50) | Источник оплаты |
| `vpn_repair_needed` | Boolean | **Ключевое поле** — нужен ли ремонт VPN-доступа |
| `vpn_repair_reason` | Text | Причина ремонта |
| `vpn_repair_marked_at` | DateTime | Когда помечен ремонт |
| `is_blocked` | Boolean | Заблокирован ли пользователь |
| `referred_by_user_id` | FK → users.id | Кто пригласил |
| `ref_code` | String(32), unique | Реферальный код |
| `referral_bonus_granted` | Boolean | Получен ли реферальный бонус |
| `referral_earned_total_rub` | int | Заработано реферальных рублей |
| `balance_rub` | int | **Ключевое поле** — баланс в рублях |
| `balance_reserved_rub` | int | Зарезервированный баланс |
| `referral_balance_migrated_at` | DateTime | Миграция реферального баланса |
| `last_activity_at` | DateTime | Последняя активность |
| `created_at` | DateTime | Дата создания |

### VpnClient (`vpn_clients`)

VPN-клиент (устройство).

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | int | PK |
| `user_id` | FK → users.id | Владелец |
| `protocol` | String(50) | "vless", "trojan" |
| `client_uuid` | String(255), unique | UUID клиента |
| `email` | String(255), unique | Email (метка клиента в 3x-ui) |
| `xui_client_id` | String(255) | ID в панели 3x-ui |
| `client_data` | Text | JSON с метаданными (страна, ссылки, настройки) |
| `created_at` | DateTime | Дата создания |

### VpnClientActivation (`vpn_client_activations`)

Активации клиентов с fingerprint-дедупликацией.

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | int | PK |
| `vpn_client_id` | FK → vpn_clients.id | Клиент |
| `user_id` | FK → users.id | Пользователь |
| `country_code` | String(10) | Страна |
| `fingerprint_hash` | String(64), index | Хеш отпечатка устройства |
| `device_label` | String(255) | Метка устройства |
| `platform` | String(50) | Платформа |
| `activation_count` | int | Счётчик активаций |

### PaymentRecord (`payment_records`) — в `dashboard/models.py`

Запись платежа.

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | int | PK |
| `user_id` | FK → users.id | Пользователь |
| `created_by_admin_id` | FK → dashboard_admins.id | Создан админом |
| `external_payment_id` | String(255) | Внешний ID платежа |
| `tariff_code` | String(50) | Код тарифа |
| `payment_method` | String(50) | "platega_sbp", "stars", "sbp_manual", "crypto_manual", "crypto_pay" |
| `payment_status` | String(50) | "pending", "confirmed", "rejected", "expired" и др. |
| `amount` | int | Сумма |
| `list_price_amount` | int | Полная цена |
| `balance_reserved_amount` | int | Списано с баланса |
| `balance_applied_amount` | int | Применено с баланса |
| `currency` | String(20) | "RUB" |
| `duration_days` | int | Дней подписки |
| `metadata_json` | Text | JSON метаданные |
| `reviewed_by_actor_id` | String(255) | Кто подтвердил |
| `reviewed_at` | DateTime | Когда подтверждено |
| `rejection_reason` | Text | Причина отказа |
| `expires_at` | DateTime | Срок действия счёта |
| `confirmed_at` | DateTime | Когда подтверждён |

### DeviceSlotEntitlement (`device_slot_entitlements`)

Право на дополнительный слот устройства.

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | int | PK |
| `user_id` | FK → users.id | Пользователь |
| `payment_record_id` | FK → payment_records.id | Платёж |
| `slots_count` | int | Количество слотов |
| `unit_price_rub` | int | Цена за слот |
| `total_amount_rub` | int | Итого |
| `expires_at` | DateTime | Срок действия |
| `status` | String(30) | "active" |

### SupportTicket (`support_tickets`)

Обращение в поддержку.

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | int | PK |
| `user_id` | BigInteger, unique | Telegram ID клиента |
| `username` | String(255) | Username |
| `full_name` | String(255) | Полное имя |
| `status` | String(50) | "new", "in_progress", "closed" |
| `assigned_admin_id` | BigInteger | Назначенный админ |
| `last_message_preview` | Text | Превью последнего сообщения |

### SupportTicketMessage (`support_ticket_messages`)

Сообщения в тикете.

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | int | PK |
| `ticket_id` | FK → support_tickets.id | Тикет |
| `role` | String(20) | "user" или "admin" |
| `sender_id` | BigInteger | ID отправителя |
| `content_type` | String(50) | "text", "photo", "video", "audio" |
| `text` | Text | Текст сообщения |
| `attachment_file_id` | String(255) | Файл вложения |

### PromoCode (`promo_codes`)

Промокоды.

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | int | PK |
| `code` | String(64), unique | Код промо |
| `kind` | String(32) | "discount_percent" |
| `discount_percent` | int | Процент скидки |
| `grant_days` | int | Дней доступа |
| `max_redemptions` | int | Макс. использований |
| `redeemed_count` | int | Сколько раз использован |
| `status` | String(32) | "active", "expired" |
| `expires_at` | DateTime | Срок действия |

### DeviceCompensationJob (`device_compensation_jobs`)

Асинхронные задачи компенсации устройств.

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | int | PK |
| `action` | String(64) | "cleanup_created_device", "finalize_created_device", "restore_deleted_device" |
| `status` | String(32) | "pending", "processing", "completed", "failed" |
| `user_id` | FK → users.id | Пользователь |
| `vpn_client_id` | FK → vpn_clients.id | VPN-клиент |
| `request_id` | String(64) | ID запроса |
| `dedupe_key` | String(255) | Ключ дедупликации |
| `attempt_count` | int | Счётчик попыток |
| `next_attempt_at` | DateTime | Следующая попытка |

### VpnRepairEvent (`vpn_repair_events`)

События ремонта VPN.

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | int | PK |
| `user_id` | FK → users.id | Пользователь |
| `result` | String(32) | "success", "failed" |
| `reason` | String(255) | Причина |

### ControlNotificationEvent (`control_notification_events`)

Системные уведомления для control-бота.

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | int | PK |
| `category` | String(50), index | "access", "payments", "system", "nodes" |
| `severity` | String(20), index | "INFO", "WARNING", "CRITICAL" |
| `event_type` | String(100), index | Тип события |
| `title` | String(255) | Заголовок |
| `message` | Text | Текст |

### Analytics-модели

| Модель | Таблица | Описание |
|--------|---------|----------|
| `AnalyticsUserAttribution` | `analytics_user_attribution` | Источник привлечения (first/last source) |
| `AnalyticsEvent` | `analytics_events` | События воронки |
| `AnalyticsDailyStageCount` | `analytics_daily_stage_counts` | Ежедневные этапы воронки |
| `AnalyticsDailyRevenue` | `analytics_daily_revenue` | Ежедневная выручка |
| `AnalyticsDailyStageSegment` | `analytics_daily_stage_segments` | Сегменты по new/returning |
| `AnalyticsDailyRevenueSegment` | `analytics_daily_revenue_segments` | Сегменты выручки |
| `AnalyticsDailyConnection` | `analytics_daily_connection` | Статистика подключений |
| `AnalyticsDailyPaymentFailureReason` | `analytics_daily_payment_failure_reasons` | Причины сбоев оплаты |
| `AnalyticsDailyAttributionIntegrity` | `analytics_daily_attribution_integrity` | Качество атрибуции |
| `AnalyticsCohortRetention` | `analytics_cohort_retention` | Когортный анализ (trial, subscription) |
| `AnalyticsRefreshState` | `analytics_refresh_state` | Состояние обновления |
| `AnalyticsHourlyOpsIncident` | `analytics_hourly_ops_incidents` | Почасовые инциденты |
| `AnalyticsHourlyOpsSnapshot` | `analytics_hourly_ops_snapshots` | Сводка состояния системы |
| `AnalyticsRuntimeStatus` | `analytics_runtime_status` | Runtime-статусы (healthy/degraded/critical) |

### Дополнительные модели backend

| Модель | Таблица | Описание |
|--------|---------|----------|
| `PublicSubscriptionLink` | `public_subscription_links` | Токенизированные ссылки на подписку |
| `PublicSubscriptionRoute` | `public_subscription_routes` | Маршруты подписки (country + slot) |
| `UserBalanceEvent` | `user_balance_events` | События изменения баланса |
| `Referral` | `referrals` | Реферальные связи |
| `ReferralReward` | `referral_rewards` | Реферальные награды |
| `PromoCodeRedemption` | `promo_code_redemptions` | Использование промокодов |
| `UserDeletionJob` | `user_deletion_jobs` | Задачи удаления пользователей |
| `ControlBroadcastCampaign` | `control_broadcast_campaigns` | Рассылки |
| `ControlBroadcastDelivery` | `control_broadcast_deliveries` | Доставки рассылок |
| `ControlTriggerRule` | `control_trigger_rules` | Правила автотриггеров |
| `ControlTriggerDeliveryLog` | `control_trigger_delivery_logs` | Логи триггеров |
| `ControlMessageTemplate` | `control_message_templates` | Шаблоны сообщений |
| `ControlAdminNotificationPreference` | `control_admin_notification_preferences` | Настройки уведомлений |
| `ChannelContentItem` | `channel_content_items` | Посты канала |
| `ChannelPostTouch` | `channel_post_touches` | Переходы по постам |

## Функции аналитики

Файл: `backend/core/analytics.py` (~2458 строк)

### Ключевые функции

| Функция | Описание |
|---------|----------|
| `upsert_user_attribution()` | Записать источник привлечения пользователя (first/last source, channel_item_id) |
| `emit_analytics_event()` | Эмитить аналитическое событие с дедупликацией (dedupe_key) |
| `emit_bot_start_event()` | Записать /start с атрибуцией источника |
| `emit_link_touched_event()` | Записать переход по ссылке канала |
| `refresh_analytics_rollups()` | Пересчитать ежедневные и почасовые агрегаты |
| `prune_analytics_events()` | Удалить старые события (retention: 180 дней) |

### Типы событий аналитики

- `user_first_seen`, `bot_start`, `link_touched`, `channel_membership_confirmed`
- `trial_started`, `onboarding_started`, `onboarding_completed`
- `connection_started`, `connection_ready`, `config_requested`, `config_issued`, `config_issue_failed`
- `payment_started`, `payment_success`, `payment_failed`
- `first_connection_success`, `connection_failed`
- `subscription_expired`, `subscription_activated`, `subscription_renewed`

### Источники атрибуции

- `organic_bot` — органический заход через бота
- `channel_post` — переход по посту канала (channel_content_items + deep_link_token)

## Миграции схемы БД

Файл: `backend/core/schema.py` (~1296 строк)

С апреля 2026 миграции используют registry применённых шагов (`schema_migration_steps`), а не слепой повторный прогон ALTER.

- **96+ шагов миграции** (`CORE_SCHEMA_MIGRATIONS`) — от `core_001` до `core_096+`
- Каждый шаг: `SchemaMigrationStep(key, statement, verify_query)`
- Verify query проверяет, что миграция уже применена
- 40+ требуемых колонок на 15+ таблицах
- 50+ требуемых индексов

### Функция `ensure_schema()`

Вызывается при старте каждого бота и dashboard:
```python
await ensure_schema()  # создаёт таблицы, применяет миграции
```

## API endpoints

Основной API находится в `dashboard/main.py` (FastAPI, порт 8088). Backend сам по себе не exposes HTTP endpoints — он библиотека моделей и логики, которую импортируют боты и dashboard. API-поверхкость обеспечивает dashboard.

### Auth

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/login` | Страница входа (Jinja) |
| POST | `/login` | Запрос кода входа (отправка через бота) |
| GET | `/verify` | Страница верификации (Jinja) |
| POST | `/verify` | Подтверждение кода → сессия |
| POST | `/logout` | Завершение сессии |

### Пользователи

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/dashboard/users` | Список пользователей |
| GET | `/dashboard/users/{user_id}` | Детали пользователя |
| POST | `/dashboard/users/{user_id}/trial` | Выдать trial |
| POST | `/dashboard/users/{user_id}/extend` | Продлить подписку |
| POST | `/dashboard/users/{user_id}/block` | Заблокировать/разблокировать |
| POST | `/dashboard/users/{user_id}/protocol` | Сменить протокол |
| POST | `/dashboard/users/{user_id}/devices/create` | Создать устройство |
| POST | `/dashboard/users/{user_id}/devices/{device_id}/delete` | Удалить устройство |
| POST | `/dashboard/users/{user_id}/delete` | Удалить пользователя |

### Поддержка

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/dashboard/support` | Список тикетов |
| GET | `/dashboard/support/{ticket_user_id}` | Детали тикета |
| POST | `/dashboard/support/{ticket_user_id}/assign` | Назначить админа |
| POST | `/dashboard/support/{ticket_user_id}/transfer` | Передать тикет |
| POST | `/dashboard/support/{ticket_user_id}/reply` | Ответить |
| POST | `/dashboard/support/{ticket_user_id}/close` | Закрыть тикет |

### Платежи

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/dashboard/payments` | Список платежей |
| POST | `/dashboard/payments/create` | Создать платёж |
| POST | `/dashboard/payments/{record_id}/confirm` | Подтвердить |
| POST | `/dashboard/payments/{record_id}/reject` | Отклонить |

### Финансы

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/dashboard/finance` | Обзор финансов |
| POST | `/dashboard/finance/create` | Создать запись |
| POST | `/dashboard/finance/{entry_id}/approve` | Утвердить |
| POST | `/dashboard/finance/{entry_id}/cancel` | Отменить |
| POST | `/dashboard/finance/report` | Отчёт |

### Серверы

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/dashboard/servers` | Список серверов |
| POST | `/dashboard/servers/create` | Добавить сервер |
| POST | `/dashboard/servers/{server_id}/status` | Обновить статус |

### v2 API (для dashboard/ui — Next.js)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/dashboard/api/v2/overview` | Обзорная страница |
| GET | `/dashboard/api/v2/users` | Список пользователей |
| GET | `/dashboard/api/v2/users/{user_id}` | Детали пользователя |
| GET | `/dashboard/api/v2/payments` | Платежи |
| GET | `/dashboard/api/v2/servers` | Серверы |
| GET | `/dashboard/api/v2/support` | Поддержка |
| GET | `/dashboard/api/v2/traffic` | Трафик |
| GET | `/dashboard/api/v2/settings` | Настройки |
| GET | `/dashboard/api/v2/promocodes` | Промокоды |
| GET | `/dashboard/api/v2/notifications` | Уведомления |
| GET | `/dashboard/api/v2/search` | Поиск |
| POST | `/dashboard/api/v2/login` | Логин (v2) |
| POST | `/dashboard/api/v2/verify` | Верификация (v2) |

### Internal API (webhook'и)

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/dashboard/api/internal/channel/generate` | Генерация поста канала |
| POST | `/dashboard/api/internal/channel/publish` | Публикация поста |
| POST | `/dashboard/api/internal/daily-news/items/upsert` | Daily news upsert |

## Таблица файлов backend/core/

| Файл | Строк | Описание |
|------|-------|----------|
| `models.py` | 922 | Все SQLAlchemy модели (User, VpnClient, Payment, Analytics и т.д.) |
| `database.py` | 17 | Async-подключение к PostgreSQL (engine, async_session, Base) |
| `schema.py` | 1296 | Миграции схемы БД, `ensure_schema()`, `REQUIRED_SCHEMA_COLUMNS`, `REQUIRED_SCHEMA_INDEXES` |
| `analytics.py` | 2458 | Аналитика: события, воронки, когорты, revenue, attribution, ops snapshots |
| `promo_codes.py` | — | Промокоды: создание, применение, gift-подписки |
| `synthetic_users.py` | — | Bridge-users (test, smoke, seed, manual_payment) |
| `tracing.py` | — | Трассировка запросов (X-Request-ID, trace propagation) |
