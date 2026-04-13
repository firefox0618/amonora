# FEATURES

## Что умеет система

### Client UI (`client_ui/`)

Отдельный проект на React/TypeScript — исходники tokenized client page.
Публикуется как статика в `landing/static/client-app/`.

- SPA с статусом подписки, QR-кодом, install-flow
- Platform-specific установки: Android, iOS, Windows, macOS, Linux, Apple TV, Android TV
- Happ feed (client-aware по headers/UA)
- Server list: `#1 Германия`, `#1 Дания`, `#1 Эстония`, `#1 Обход белых списков`

### Клиентский бот (`@amonora_bot`)

- Trial (один раз, при подписке на канал)
- Создание / удаление / переименование устройств
- Выбор страны → выбор режима (`Стабильный / Мобильный / Резерв`)
- Ключи `VLESS` / `Trojan` + QR
- Подписка: продление, статус
- Оплата: `Telegram Stars`, Platega (СБП/крипто auto), ручной fallback
- Внутренний Баланс (RUB) — авто-списание при оплате
- Реферальная система (50₽ / 100₽ за 12м)
- Промокоды / подарочные подписки
- User-level subscription page: `client.amonoraconnect.com/<token>`
- Переход в `@amonora_support_bot`

### Support-бот (`@amonora_support_bot`)

- Приём обращений, создание тикетов
- Диалоги с клиентами, медиа (фото/видео/аудио)
- Назначение ответственного, передача, закрытие
- Полная история в БД без автоудаления

### Control-бот (`@amonora_control_bot`)

- Системные уведомления (платежи, auth-коды, node alerts)
- Review ручных оплат (confirm/reject)
- 5-минутные коды входа в админку
- Быстрые действия: sync / deep repair / trial / extend / block
- Рассылки и триггеры (admin push, user campaigns)
- Per-admin notification preferences
- Support-действия через те же backend-seams, что и dashboard

### Панель управления (`dashboard` + `dashboard/ui`)

- Вход: логин/пароль + Telegram-код
- Роли: Владелец / Тех. администратор / Менеджер
- Пользователи: просмотр, фильтр, детальная карточка
- Устройства: создание, удаление, status-проверка, sync, deep repair
- Платежи: подтверждение/отклонение, reconcile, balance history
- Поддержка: тикеты, медиа-вложения
- Серверы: статус, health check, restart, maintenance
- Аналитика: кампании, funnel, attribution
- Промокоды: создание, просмотр активаций
- Audit log: журнал действий

### Публичный сайт (`amonoraconnect.com`)

- Витрина продукта, тарифы, FAQ
- Bridge-access: бесплатный ключ на 24 часа (если Telegram недоступен)
- Provider callback для Platega
- Tokenized subscription page: `client.amonoraconnect.com/<token>`
  - Браузер → HTML-страница со статусом, install-flow, QR
  - Happ → subscription feed с того же URL
  - Server-side bind к слотам `1..N`, сохранение device metadata
- Hidden `/manual` — инструкция по подключению

### VPN-ноды

| Нода | Runtime | Режимы |
|------|---------|--------|
| Германия (3x-ui) | `VLESS + Reality + TCP` | Стабильный / Мобильный / Резерв |
| Дания (Xray core) | `VLESS + Reality + XHTTP` | Стабильный / Мобильный / Резерв |
| Эстония (reserve) | `VLESS + Reality + TCP` | Только unified-link/feed |

### Операторские возможности

- Фильтр пользователей: по статусу, тарифу, периоду
- Device status: `🟢 Исправен / 🔴 Сломан` с причиной
- Payment reconcile: auto-refresh Platega записей
- Analytics: кампании, funnel, attribution, когорты
- Grafana: pre-aggregated rollup tables, read-only datasource
