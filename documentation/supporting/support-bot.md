# Support Bot

> Supporting reference document. Use [PROJECT_OVERVIEW.md](/home/dextrmed/projects/amonora_bot/documentation/PROJECT_OVERVIEW.md), [DOMAIN.md](/home/dextrmed/projects/amonora_bot/documentation/DOMAIN.md) and [FEATURES.md](/home/dextrmed/projects/amonora_bot/documentation/FEATURES.md) as canonical current-state docs first.

## Роль support-бота

`@amonora_support_bot` — отдельный канал общения с клиентом.

Он нужен, чтобы:

- не смешивать поддержку с основным ботом
- вести обращения в отдельном потоке
- позже подключить AI / n8n

## Текущий сценарий

1. Клиент пишет в support-бот.
2. Сообщение превращается в тикет.
3. Админы получают карточку обращения.
4. Один из админов берёт диалог.
5. Ответы уходят клиенту обратно через support-бота.

Важно:

- auth-коды в Панель управления больше не идут сюда;
- ручной review оплат больше не идёт сюда;
- node / infra alerts больше не идут сюда.

## Что уже поддерживается

- статус `новый / в работе / закрыт`
- назначение ответственного
- передача другому админу
- история диалога
- reply на карточку обращения
- хранение attachment metadata для Telegram-вложений
- пересылка фото / видео / аудио операторам как реальных медиа

## Что сознательно вынесено в Amonora Control

- системные уведомления;
- auth-коды дашборда;
- очередь ручных оплат;
- `confirm / reject` ручных платежей;
- node / watchdog alerts;
- внутренние payment/access/system errors.

## Хранение данных

История тикетов и карточки обращений теперь хранятся в PostgreSQL:

- таблица `support_tickets`
- таблица `support_ticket_messages`

Это важно помнить при переносе сервера: переносить нужно не JSON-файл, а дамп основной БД.

## Что важно по логам

Лишние пользовательские тексты не должны шуметь в системных логах.

В журнале должны оставаться в основном:

- ошибки
- падения
- важные системные предупреждения

## Куда развивается support

Следующий слой:

- AI first line
- fallback на человека
- теги обращений
- приоритеты
- автоматические уведомления
