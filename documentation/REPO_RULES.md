# REPO RULES

## Что считается архитектурой

| Директория | Роль |
|------------|------|
| `backend` | Общее ядро: модели, схема БД |
| `bot` | Клиентский продуктовый flow |
| `support_bot` | Support-операции |
| `control_bot` | Internal notifications |
| `dashboard` | Административный backend + API |
| `dashboard/ui` | Next.js frontend админки |
| `client_ui` | Исходники tokenized client page (публикуется как `landing/static/client-app`) |
| `landing` | Публичный сайт |
| `ops` | Эксплуатация: systemd, nginx, backups |
| `documentation` | Каноническая документация |
| `test_bot` | Тестовый бот для мобильных профилей |
| `tests` | Тесты проекта (135+ файлов) |

## Что НЕ считается архитектурой

- `.git`, `venv`, `__pycache__`, `dashboard/ui/.next`, `dashboard/ui/node_modules`
- Временные markdown, рабочие картинки, автогенерируемые кеши

## Legacy

- Jinja UI внутри `dashboard` (сохраняется для совместимости)
- Старые маршруты админки — compatibility redirects

## Черновики

Любые markdown-файлы вне `documentation/` и корневых файлов проекта (`README.md`, `AGENTS.md`) — черновики.

## Корневые файлы проекта

| Файл | Что делает |
|------|-----------|
| `.env.example` | Шаблон переменных окружения |
| `requirements.txt` | Python-зависимости |
| `AGENTS.md` | Правила для AI-агентов |
| `LICENSE` | Лицензия проекта |
| `README.md` | Краткое описание проекта |
| `reconcile_vpn_regions.py` | Скрипт сверки VPN-регионов (dry-run/apply) |
| `amonora_control_tz_v4.md`, `v5.md` | Технические задания на control-бота |

## Технологии

- **Python 3.12** — основной язык
- **aiogram 3** — Telegram боты
- **FastAPI** — backend API
- **SQLAlchemy 2.0 + asyncpg** — работа с БД
- **PostgreSQL** — база данных
- **Next.js** — frontend админки
- **3x-ui API** — управление VPN Germany/Estonia
- **Xray core** — VPN runtime Denmark
- **systemd** — запуск сервисов
- **Nginx** — маршрутизация трафика
- **Dashboard analytics** — операторская аналитика
- **n8n** — автоматизация каналов
- **Jinja2** — legacy UI шаблоны
- **pillow, qrcode** — генерация QR-кодов

## Эксплуатация

- `ops/` — systemd, nginx, env, watchdog, reminders, скрипты
- Backups — server-side, вне git (на хостах)

## Тесты

Папка `tests/` содержит 135+ тестовых файлов. Основные группы:

| Группа | Что проверяет |
|--------|--------------|
| `test_db.py`, `test_subscription.py` | Базовые модели и подписки |
| `test_xui.py`, `test_xui_key_limit.py` | Интеграция с 3x-ui |
| `test_xray_single_ip_enforcer.py` | Denmark IP enforcement |
| `test_manual_payments.py`, `test_payment_finalization.py` | Платежи |
| `test_platega*.py` | Platega интеграция |
| `test_referral*.py` | Реферальная система |
| `test_dashboard*.py` | Dashboard API v2 и UI |
| `test_landing*.py` | Публичный сайт |
| `test_region*.py`, `test_vpn_regions*.py` | VPN-регионы |
| `test_trial*.py` | Trial flow |
| `test_support*.py` | Поддержка |
| `test_device*.py` | Устройства |
| `test_server_watchdog.py` | Watchdog |
| `test_ops*.py` | Ops-скрипты |

Запуск: `./venv/bin/python -m unittest discover -s tests -p 'test_*.py'`

## Структура документации

| Папка | Что внутри |
|-------|-----------|
| `ai/` | AI-контекст: PROJECT_CONTEXT, STATE, STACK_RULES, PHASES |
| `ai/TASKS/` | 230+ файлов задач (NNN-name.md + NNN-name-result.md) |
| `ops/` | Операционные документы, CHANGELOG |
| `vpn/` | VPN-стратегия, клиентские конфиг-паки |
| `product/` | Продуктовые карты |
| `strategy/` | Roadmap |
| `business/` | Growth / GTM / бизнес-модели |
| `supporting/` | Reference документы (не canonical) |
| `archive/` | Исторические снапшоты |

## Source of truth

| Что | Где |
|-----|-----|
| Данные | PostgreSQL |
| Код | Реальный runtime в репозитории |
| Документация | `documentation/` |

Приоритет: код → документация → черновики.

## Спорная зона: dashboard vs dashboard/ui

- `dashboard/ui` — основной UI админки
- `dashboard` — обязательный backend админки
- Jinja UI — legacy, но не удаляется без проверки покрытия

## Спорная зона: backend vs логика в приложениях

Ядро распределено: `backend` + часть логики в `bot`, `dashboard`, `support_bot`.
`backend` — центр ядра, но не единственное место доменной логики.

## Порядок чтения репозитория

1. `PROJECT_OVERVIEW.md`
2. `ARCHITECTURE.md`
3. `DOMAIN.md`
4. `RUNBOOK.md`
5. `FEATURES.md`
6. Runtime-код
7. `ops/`

## Правила изменения кода

- Не считать `dashboard` полностью legacy
- Не удалять Jinja UI без проверки покрытия в `dashboard/ui`
- Не менять runtime-пути, systemd, nginx без обновления `RUNBOOK.md`
- Любое изменение source-of-truth моделей → проверка всех связанных flow
