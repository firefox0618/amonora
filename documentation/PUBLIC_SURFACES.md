# PUBLIC SURFACES

## Публичные точки входа

| Поверхность | URL / Handle | Назначение |
|-------------|-------------|-----------|
| Основной бот | `@amonora_bot` | Клиентский вход в продукт |
| Бот поддержки | `@amonora_support_bot` | Обращения клиентов |
| Сайт | `amonoraconnect.com` | Витрина, bridge-access, legal |
| Канонический web-entry | `www.amonoraconnect.com` | Основной хост для мобильных сетей |
| Subscription page | `client.amonoraconnect.com/<token>` | User-level страница + Happ feed |
| Happ wrapper | `client.amonoraconnect.com/happ/add?sub=...` | Открытие Happ без внешнего proxy |
| Bridge-access | `POST /bridge/access` | Временный ключ на 24 часа |
| Platega webhook | `POST /webhooks/platega/{secret}` | Provider callback для auto-оплат |
| Инструкция | `/manual` | Скрытая страница (по прямой ссылке) |
| Канал | `@amonora_new` | Новости, анонсы |
| Email | `amonoraconnect@yandex.ru` | Обратная связь, претензии |

## Не являются публичными поверхностями

| Поверхность | Почему |
|-------------|--------|
| `@amonora_control_bot` | Internal admin-only |
| `@amonora_v_2_0_bot` | Тестовый бот, не канонический вход |
| `https://amonoraconnect.com/n8n/` | Operator-only, Basic Auth |
| `https://grafana.amonoraconnect.com/` | Operator-only, Basic Auth, read-only datasource |

## Tokenized subscription page (`client.amonoraconnect.com/<token>`)

- Canonical URL: `/<token>`
- Браузер → HTML: статус подписки, срок, install-flow, QR + copy
- Happ → subscription feed (client-aware по headers/UA)
- Compatibility route: `/sub/<token>` (fallback, не раздаётся пользователям)
- Server-side: bind к слотам `1..N` (N = effective device limit), сохранение `модель / ОС / версия ОС`
- Server list: `#1 Германия`, `#1 Дания`, `#1 Эстония` (reserve), `#1 Обход белых списков`
- Install-flow: `Android`, `iOS`, `Windows`, `macOS`, `Linux`, `Apple TV`, `Android TV` — с официальными ссылками

## Bridge-access

- Сайт выдаёт бесплатный ключ на 24 часа, если Telegram недоступен
- Это мост до `@amonora_bot`, не отдельный тариф
- Rate-limited на nginx уровне
- Synthetic bridge-users не попадают в обычные агрегаты панели

## Отзывы

Официального канала отзывов пока нет. Открытая продуктовая зона.
Формальная обратная связь: `amonoraconnect@yandex.ru`.
