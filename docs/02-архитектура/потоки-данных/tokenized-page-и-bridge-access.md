# Детализация: Tokenized Subscription Page и Bridge-Access

## Tokenized Subscription Page

**URL:** `client.amonoraconnect.com/<token>`

Это единая точка доступа клиента к подписке. Одна страница обслуживает два типа клиентов:

### Браузер → HTML

| Что видит | Описание |
|-----------|----------|
| Статус подписки | Активна / истекла / не активна |
| Оставшиеся дни | Сколько дней до окончания |
| Тариф | Название текущего тарифа |
| QR-код | Для сканирования Happ-клиентом |
| Install-flow | Инструкции по установке Happ для 7 платформ |

### Happ-клиент → Subscription Feed

Happ распознаётся по User-Agent (`happ`, `happ-proxy` и т.д.). Вместо HTML отдаётся plain-text feed со списком всех connection URI:

```
vless://... (Германия #1)
vless://... (Германия #2)
vless://... (Германия #3)
vless://... (Дания #1)
vless://... (Дания #2)
vless://... (Дания #3)
vless://... (Эстония #1, reserve)
```

### Server-side Binding

При первом обращении Happ делает запрос на `/sub/<token>` → сервер привязывает устройство к слоту `1..N` (где N = эффективный лимит устройств). Сохраняются:
- Модель устройства
- ОС
- Версия ОС

### Server List

| Сервер | Код | Статус |
|--------|-----|--------|
| Германия | DE | Основной |
| Дания | DK | Основной (anti-DPI) |
| Эстония | EE | Reserve |
| Обход белых списков | — | Дополнительный |

### Платформы Install-Flow

Android, iOS, Windows, macOS, Linux, Apple TV, Android TV.

## Bridge-Access

**Endpoint:** `POST /bridge/access` на `amonoraconnect.com`

### Зачем

Если Telegram недоступен (блокировки, сбои), пользователь получает бесплатный ключ на 24 часа через сайт.

### Как работает

1. Клиент делает POST-запрос на `/bridge/access`
2. Сервер создаёт **синтетического пользователя** (`is_synthetic=True`)
3. Создаёт `PublicSubscriptionLink` с токеном
4. Возвращает connection URI на 24 часа

### Ограничения

- Rate-limited на уровне nginx
- Синтетические bridge-users **не попадают** в обычные агрегаты панели
- Это мост до `@amonora_bot`, не отдельный тариф
- После восстановления доступа к Telegram — пользователь возвращается в бота

## Happ Wrapper

**URL:** `client.amonoraconnect.com/happ/add?sub=<page_url>`

Открывает Happ без внешнего proxy:
1. Показывает страницу со ссылкой подписки
2. Через 180мс открывает `happ://add/<page_url>` (deep link)
3. Если Happ не установлен — кнопки для скачивания

## Non-Public Surfaces

| Поверхность | URL | Доступ |
|-------------|-----|--------|
| Контрол-бот | `@amonora_control_bot` | Admin-only |
| n8n | `amonoraconnect.com/n8n/` | Basic Auth |
| Dashboard | Внутренний | Логин/пароль + Telegram-код |
| Dashboard API | `127.0.0.1:8088` | Сервер-only (nginx) |
