# Amonora Control Bot

> Supporting reference document. Use [PROJECT_OVERVIEW.md](/home/dextrmed/projects/amonora_bot/documentation/PROJECT_OVERVIEW.md), [ARCHITECTURE.md](/home/dextrmed/projects/amonora_bot/documentation/ARCHITECTURE.md), [DOMAIN.md](/home/dextrmed/projects/amonora_bot/documentation/DOMAIN.md) and [RUNBOOK.md](/home/dextrmed/projects/amonora_bot/documentation/RUNBOOK.md) as canonical current-state docs first.

## Роль

`@amonora_control_bot` — внутренний Telegram-бот команды.

Он нужен для того, чтобы:

- отделить системные и административные события от клиентской поддержки;
- получать auth-коды для входа в Панель управления;
- вести review ручных оплат;
- получать node / infra alerts;
- видеть user lifecycle и access события без входа в веб-панель;
- быстро открывать пользователя, тикет, платёж или ноду и выполнить базовое операционное действие прямо из Telegram.

## Что входит в Amonora Control

- платежи:
  - новая ручная заявка;
  - подтверждение;
  - отклонение;
  - ошибки `payment -> access`;
- авторизация:
  - коды входа в Панель управления;
  - masked history последних auth-событий;
- ноды и инфраструктура:
  - `offline`;
  - `degraded`;
  - `overloaded`;
  - `recovered`;
- пользователи и доступ:
  - новый пользователь;
  - trial;
  - продление;
  - выдача / перевыпуск ключа;
  - provisioning/access failures;
- support:
  - список обращений;
  - open / assign / reply / transfer / close;
  - linked user/payment context;
- системные ошибки и служебные события.

Support по-прежнему физически живёт в `@amonora_support_bot`, но `@amonora_control_bot` теперь умеет работать с теми же тикетами через общие backend/storage seams.

## Команды

- `/start`
- `/dashboard`
- `/status`
- `/nodes`
- `/payments`
- `/users`
- `/user`
- `/problems`
- `/support`
- `/alerts`
- `/login_codes`
- `/notifications`
- `/events`
- `/settings`
- `/broadcast`
- `/help`

## Экраны и shell

Текущий bot-shell разделён на рабочие экраны:

- `Дашборд`
- `Ноды`
- `Платежи`
- `Пользователи`
- `Проблемы`
- `Поддержка`
- `Коды входа`
- `Уведомления`
- `События`
- `Рассылка / Триггеры`
- `Помощь`

Важно:

- в стартовом shell есть профиль и срез `требует внимания`;
- `Проблемы` собирают payment queue, repair-needed users, support backlog и node issues в одном месте;
- `Поддержка` больше не вынесена только в `@amonora_support_bot`: внутри `@amonora_control_bot` доступны open/assign/reply/transfer/close по тем же ticket-данным;
- `Ошибки` / `/alerts` остаются как совместимый severity/history экран, но уже не являются главным entrypoint;
- `Платежи` не ведут в Панель управления: review открывается и подтверждается прямо внутри Telegram;
- входящие ручные заявки на оплату приходят сразу live-сообщением с inline-кнопками `Подтвердить / Отклонить`;
- `/user` открывает реальную user-card с actions `sync / deep repair / trial / extend / block / clear-access`;
- `Ноды` дают detail-focus и быстрые действия `health check / restart / maintenance / resync(refresh)`;
- `Коды входа` показывают masked auth history и активные dashboard sessions.

Все экраны используют только реальные агрегаты из текущего backend-контура:

- `dashboard.services`
- `dashboard.v2_data`
- `ControlNotificationEvent`
- `DashboardSession`
- `PaymentRecord`
- user/access/device данные из PostgreSQL

Макетные метрики вроде `open rate`, `read time` и `99.99% uptime` сознательно не показываются, потому что текущий стек их не измеряет.

## Роли

Поддерживаются роли:

- `owner`
- `admin`
- `operator`
- `support-view-only`

Минимальные правила:

- бот доступен только allowlist Telegram ID;
- `support-view-only` не получает destructive actions;
- `confirm / reject` ручных оплат доступны только `owner / admin / operator`.
- owner-only блок `Рассылка / Триггеры` видит только `owner`;
- `Настройки` доступны всем control-admin, но управление чужими notification preferences доступно только `owner`.
- в продуктовых терминах `admin` соответствует `Тех. администратору`, а `operator` соответствует `Менеджеру`.

## Настройки уведомлений

`Настройки` используют per-admin preferences поверх глобальных env-флагов категорий.

Приоритет доставки такой:

1. глобальные env category toggles;
2. per-admin DB preferences;
3. `night critical only`, если он включён.

Source of truth:

- `ControlAdminNotificationPreference`

Категории:

- `payments`
- `users`
- `support`
- `nodes`
- `security`
- `system`

Часть категорий жёстко обязательна по роли и не может быть отключена из интерфейса:

- `owner` / `admin`: `payments`, `users`, `nodes`, `security`, `system`;
- `operator`: `payments`, `users`, `support`, `security`;
- `support-view-only`: `support`.

Legacy categories `access / panel_auth / errors` продолжают существовать в event-log, но в notification preferences они сводятся в новые buckets.

## Рассылка и триггеры

Owner-only экран `Рассылка / Триггеры` даёт 5 рабочих блоков:

- `Push админам`
- `Ручная рассылка пользователям`
- `Автоматические триггеры`
- `Шаблоны`
- `Статистика рассылок`

### Push админам

- отправляются через `@amonora_control_bot`;
- поддерживают immediate send, schedule, priority и test-send себе;
- используют `ControlBroadcastCampaign` и `ControlBroadcastDelivery`.

### Ручная рассылка пользователям

- отправляется через `@amonora_bot`;
- сегменты строятся по реальным user/access/activity/device данным;
- CTA-кнопки ограничены preset-действиями:
  - `open_tariffs`
  - `start_trial`
  - `open_support`
  - `open_channel`

### Автоматические триггеры

Текущий worker использует DB-driven `ControlTriggerRule`, а также делает periodic incident scan, и работает каждые 5 минут через:

- `amonora-access-reminders.service`
- `amonora-access-reminders.timer`

Сейчас поддерживаются:

- окончание trial;
- trial follow-up после окончания;
- `start` без действий;
- окончание платной подписки;
- длительная неактивность;
- лимит устройств;
- проблемы с доступом (`vpn_repair_needed`).

Дополнительно тот же worker теперь автоматически поднимает internal control-events по:

- деградации и падению нод;
- не-`active` состоянию ключевых локальных сервисов;
- наличию user-access инцидентов `vpn_repair_needed`.

Для user-activity source of truth используется `users.last_activity_at`, который обновляется:

- в `@amonora_bot` message/callback middleware;
- на ключевых subscription/trial действиях;
- на входящих support messages.

### Шаблоны и статистика

- шаблоны хранятся в `ControlMessageTemplate`;
- кампании — в `ControlBroadcastCampaign`;
- доставки — в `ControlBroadcastDelivery`;
- trigger-send история — в `ControlTriggerDeliveryLog`.

Честные метрики, которые сейчас действительно есть:

- `queued`
- `sent`
- `failed`
- `clicked`
- `converted`

## Delivery и хранение

- по умолчанию уведомления идут в личные сообщения разрешённым admin ID;
- plaintext auth-code живёт только в live Telegram message;
- в БД сохраняется masked version;
- source of truth для event log: `control_notification_events`.
- source of truth для user campaigns / triggers: PostgreSQL campaign + delivery tables.

## Anti-spam

- у событий есть `category`, `severity`, `event_type`, `dedupe_key`;
- одинаковые infra alerts не спамят чаще cooldown;
- recovery идёт отдельным событием и закрывает активный incident.

Для trigger/campaign sends отдельный dedupe живёт в `ControlTriggerDeliveryLog` и campaign delivery status.

## Production note

Перед production rollout нужен ротированный bot token.

Если control admin ни разу не открывал `@amonora_control_bot` и не нажал `/start`, Telegram не даст доставить ему DM-уведомление.

Если owner-пуши, user-trigger кампании или periodic incident alerts не уходят:

- проверь `AMONORA_CONTROL_BOT_TOKEN` и `BOT_TOKEN`;
- проверь, что новые таблицы созданы (`AUTO_APPLY_SCHEMA=1` или ручное `ensure_schema`);
- проверь `amonora-access-reminders.timer`, потому что scheduled campaigns и triggers завязаны на него.
