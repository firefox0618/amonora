# ARCHITECTURE

## Принцип

- **modular monolith first** — пока одна связанная система, без разделения на микросервисы
- Усложняем только после стабилизации текущего прод-контура

## Слои системы

| Слой | Компоненты |
|------|-----------|
| **Core** | `backend` (модели, схема БД), значимая логика в `bot`, `dashboard` |
| **Interfaces** | `bot`, `support_bot`, `control_bot`, `landing`, `dashboard/ui` |
| **Operations** | `ops` (systemd, nginx, backups, n8n) |
| **Infrastructure** | VPN-ноды на отдельных серверах |

## Зависимости

```
bot → backend → PostgreSQL
support_bot → backend → PostgreSQL
control_bot → backend → PostgreSQL
dashboard → backend + PostgreSQL
dashboard/ui → dashboard API → PostgreSQL
landing → backend + PostgreSQL
ops → systemd / nginx / runtime
```

## Core

### backend

Общее ядро: модели, схема БД, доменные сущности. Без него не работают ни один из сервисов.

Модули в `backend/core/`:

| Модуль | Что делает |
|--------|-----------|
| `models.py` | Основные модели: User, Payment, Device, Ticket и т.д. |
| `schema.py` | Схема БД, миграции |
| `database.py` | Подключение к PostgreSQL |
| `analytics.py` | Модели аналитики: события, воронки, когорты |
| `promo_codes.py` | Промокоды и подарочные коды |
| `synthetic_users.py` | Синтетические пользователи (bridge-users) |
| `tracing.py` | Трассировка запросов (X-Request-ID) |

С апреля 2026: schema migration использует registry применённых шагов в PostgreSQL, а не слепой повторный прогон ALTER'ов.

### dashboard

Не только UI — это полноценный backend:

- FastAPI + API для `dashboard/ui`
- auth/session логика админки
- часть управленческой логики по пользователям, платежам, серверам
- Legacy Jinja UI сохраняется для совместимости, но не является основным интерфейсом

### Источник истины

PostgreSQL — единственный source of truth. `dashboard/ui` и `landing` не хранят свою бизнес-логику.

## Interfaces

### `@amonora_bot` — клиентский бот
Trial, устройства, страны, протоколы, подписка, оплата (Stars + Platega), рефералы, баланс.

Структура `bot/`:

| Директория | Что внутри |
|------------|-----------|
| `handlers/` | Обработчики команд и кнопок |
| `keyboards/` | Клавиатуры (inline / reply) |
| `middlewares/` | Middleware (логирование активности) |
| `utils/` | Утилиты: VLESS, тарифы, тексты, регионы, QR, рефералы, слоты, режимы, доступ |
| `main.py` | Точка входа |

### `@amonora_support_bot` — поддержка
Тикеты, диалоги с клиентами, медиа. Не получает auth-коды, payment review, node alerts.

### `@amonora_control_bot` — внутренний бот команды
Системные уведомления, review платежей, коды входа, рассылки, триггеры, node alerts.

### `@test_amonora_bot` — тестовый бот
Admin-only бот для проверки мобильных профилей. Отдаёт 8 тестовых конфигов (Germany, Denmark, Estonia) только разрешённым Telegram ID. Не заменяет основной бот.

Структура `test_bot/`:

| Файл | Что делает |
|------|-----------|
| `main.py` | Точка входа |
| `router.py` | Маршруты команд |
| `profiles.py` | Генерация тестовых конфигов |
| `device_binding.py` | Привязка устройств |
| `access.py` | Проверка доступа (allowlist) |
| `assets/v2/` | Картинки для экранов |

### `amonoraconnect.com` — публичный сайт
Витрина продукта, bridge-access на 24 часа, webhook Platega, tokenized subscription page `client.amonoraconnect.com/<token>`.

### Панель управления
- **backend**: `dashboard` (FastAPI)
- **frontend**: `dashboard/ui` (Next.js) — основной рабочий UI
- Роли: Владелец / Тех. администратор / Менеджер

## VPN-ноды

| Нода | Runtime | Назначение |
|------|---------|-----------|
| Германия (`ffconnect.amonoraconnect.com`) | 3x-ui | Основная совместимая |
| Дания (`dk.amonoraconnect.com`) | Xray core (standalone) | Modern anti-DPI |
| Эстония (`est.amonoraconnect.com`) | x-ui / Xray | Скрытый reserve-регион |

VPN-ноды вынесены отдельно от backend. На них не живут: боты, dashboard, PostgreSQL.

## Operations (`ops`)

- **systemd** — запуск всех сервисов
- **nginx** — маршрутизация внешнего трафика
- **n8n** — автоматизация каналов (core host)
- **backups** — server-side, вне git

## Source of truth по коду

Приоритет чтения:
1. Реальный runtime-код (`backend`, `bot`, `support_bot`, `dashboard`, `dashboard/ui`, `landing`)
2. Каноническая документация (`documentation/`)
3. Временные заметки вне `documentation/` — черновой слой
