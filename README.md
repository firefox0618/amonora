# Amonora

Amonora - это экосистема приватного доступа и клиентских сервисов вокруг Telegram-first продукта.  
Сейчас основной фокус экосистемы - `Amonora Connect`: VPN-сервис с ботом, поддержкой, `Amonora Control`, Панелью управления, публичным сайтом и раздельной инфраструктурой по странам.

Главная документационная точка входа для текущего состояния проекта:

- [documentation/INDEX.md](documentation/INDEX.md)

Публичные точки входа:

- сайт: [https://www.amonoraconnect.com](https://www.amonoraconnect.com)
- панель управления: [https://www.amonoraconnect.com/login](https://www.amonoraconnect.com/login)
- основной бот: [https://t.me/amonora_bot](https://t.me/amonora_bot)
- бот поддержки: [https://t.me/amonora_support_bot](https://t.me/amonora_support_bot)
- бот управления: [https://t.me/amonora_control_bot](https://t.me/amonora_control_bot)
- канал: [https://t.me/amonora_vpn](https://t.me/amonora_vpn)

## Что уже работает

В проде уже работают:

- 4 Telegram-бота:
  - клиентский `@amonora_bot`
  - support-бот `@amonora_support_bot`
  - internal-бот `@amonora_control_bot`
  - тестовый бот `@test_amonora_bot` (admin-only, mobile test profiles)
- публичный лендинг `amonoraconnect.com`
- Панель управления для команды
- backend-сервер с PostgreSQL
- 3 VPN-ноды:
  - Германия — основная совместимая (`3x-ui`)
  - Дания — основная modern anti-DPI (standalone `Xray core`)
  - Эстония — скрытый reserve-регион (`x-ui` / `Xray`)
- автоматическая оплата `СБП` / крипто через `Platega` (ручной контур — emergency fallback)
- внутренний `Баланс` пользователя в RUB для оплаты подписок
- тикеты поддержки в `PostgreSQL`
- отдельная документация и операционный runbook

## Архитектура

Проект сейчас разделён на 3 независимых контура.

### 1. Backend

Backend-сервер отвечает за:

- основной бот
- support-бот
- control-бот
- панель управления
- лендинг
- PostgreSQL
- tunnel-доступ к VPN-панелям (`3x-ui` для Germany/Estonia, SSH для Denmark `Xray core`)

Это позволяет не смешивать клиентский веб/бот-слой и реальные VPN-серверы в один узел.

### 2. Telegram-боты

В проекте четыре рабочих Telegram-контура:

- `@amonora_bot` — продуктовый клиентский бот
- `@amonora_support_bot` — обработка обращений, диалогов и клиентских медиа
- `@amonora_control_bot` — системные уведомления, auth-коды и review платежей
- `@test_amonora_bot` — admin-only тестовый бот для mobile profile validation

Они используют общую БД и общую административную экосистему, но решают разные задачи.

### 3. VPN-ноды

VPN вынесен на отдельные сервера:

- Германия — основная нода (`3x-ui`)
- Дания — современная anti-DPI нода (standalone `Xray core`)
- Эстония — скрытый reserve-регион (`x-ui` / `Xray`)

Это снижает риск для backend-контуров и позволяет масштабировать локации отдельно от ботов и сайта.

## Основные возможности

### Клиентский бот

`@amonora_bot` уже умеет:

- выдавать пробный доступ;
- показывать личный кабинет;
- показывать денежный `Баланс` и пополнять его через `Platega`;
- создавать и управлять устройствами;
- работать с `VLESS` и `Trojan`;
- выбирать страну подключения и режим (`Стабильный / Мобильный / Резерв`);
- выдавать ключ и QR;
- продлевать доступ;
- принимать `Telegram Stars`;
- автоматическая оплата `СБП` / крипто через `Platega`;
- автоматически списывать Баланс в RUB-оплатах;
- поддерживать денежную реферальную систему;
- работать с промокодами и подарочными подписками.

### Support-бот

`@amonora_support_bot` уже умеет:

- принимать обращения клиентов;
- создавать и вести тикеты;
- назначать ответственного администратора;
- передавать и закрывать диалоги;
- хранить историю обращений в `PostgreSQL`;
- принимать клиентские фото, видео и аудио.

### Amonora Control

`@amonora_control_bot` уже умеет:

- принимать системные уведомления;
- показывать auth-коды для входа в Панель управления;
- делать review ручных платежей (confirm / reject);
- показывать статусы нод, alerts и user/access события;
- выполнять быстрые admin-действия: sync / deep repair / trial / extend / block;
- управлять рассылками и триггерами (admin push, user campaigns, DB-driven triggers);
- настраивать per-admin notification preferences.

### Панель управления

Веб-панель уже используется как командный центр и включает:

- обзор;
- пользователи;
- VPN;
- поддержка;
- платежи;
- серверы;
- сервисы;
- документация.

Что в нём уже можно делать:

- управлять пользователями и доступом;
- создавать и удалять устройства;
- работать с тикетами поддержки;
- подтверждать и отклонять ручные платежи;
- смотреть состояние серверов и сервисов;
- редактировать RUB-тарифы;
- вести аудит действий;
- использовать частичный финансовый учёт по доходам и расходам.

### Сайт

Публичный лендинг на `amonoraconnect.com` уже работает и используется как продуктовая витрина:

- объясняет продукт;
- ведёт в бота, поддержку и канал;
- показывает тарифы и сценарий подключения;
- содержит правовые и служебные страницы.

## Текущая инфраструктура

### Backend

- сервер: `46.21.81.186`
- роль: боты, Панель управления, сайт, PostgreSQL, tunnel к VPN-панелям

### VPN-ноды

- Германия:
  - IP: `213.108.20.34`
  - домен: `ffconnect.amonoraconnect.com`
  - статус: основная совместимая нода (`3x-ui`)
- Дания:
  - IP: `81.17.159.58`
  - домен: `dk.amonoraconnect.com`
  - статус: modern anti-DPI нода (standalone `Xray core`)
- Эстония:
  - IP: `185.88.37.71`
  - домен: `est.amonoraconnect.com`
  - статус: скрытый reserve-регион (`x-ui` / `Xray`)

### Домены

- `amonoraconnect.com` — сайт и Панель управления
- `ffconnect.amonoraconnect.com` — основная VPN-нода Германии
- `dk.amonoraconnect.com` — основная VPN-нода Дании
- `est.amonoraconnect.com` — reserve-регион Эстонии
- `client.amonoraconnect.com/<token>` — персональная единая ссылка на подписку

## Платежный контур

Сейчас в проекте используется такая модель оплаты:

- `Telegram Stars` — основной нативный способ оплаты внутри Telegram
- `Platega` (автоматическая `СБП`) — основной автоматический способ оплаты
- `Platega` (автоматическая криптовалюта) — основной автоматический способ оплаты
- `Ручная СБП` — emergency fallback с подтверждением администратором
- `Ручная крипта` — emergency fallback с подтверждением администратором
- Внутренний `Баланс` пользователя в RUB — автоматически списывается при оплате подписок

Важно:

- автоматические оплаты через `Platega` подтверждаются без ручного review;
- доступ не выдаётся до подтверждения ручной заявки;
- `Amonora Control` и Панель управления умеют подтверждать и отклонять такие заявки;
- `Crypto Pay` оставлен в коде как скрытый legacy-path и не считается активным способом оплаты.

## Панель управления

Текущая Панель управления - это не просто страница статистики, а административный слой проекта.

Сейчас в нём уже реализованы:

- двухэтапный вход: логин/пароль + код в Telegram;
- роли для администраторов;
- просмотр пользователей и их доступа;
- управление устройствами;
- платежный кабинет;
- серверный контур;
- сервисы и управление тарифами;
- документация, читаемая из GitHub/репозитория.

Текущее состояние раздела финансов:

- финансовый учёт уже частично работает внутри payments surface;
- finance-ledger виден owner / tech_admin, скрыт для менеджера;
- следующая продуктовая волна предусматривает выделенную вкладку `Финансы` с расширенной отчётностью.

## Документация и runbook

В репозитории есть отдельная папка `documentation/`, которая используется как каноническая база знаний проекта.

С чего читать в первую очередь:

- `documentation/PROJECT_OVERVIEW.md`
- `documentation/ARCHITECTURE.md`
- `documentation/DOMAIN.md`
- `documentation/REPO_RULES.md`
- `documentation/RUNBOOK.md`
- `documentation/FEATURES.md`

Ключевой файл для эксплуатации:

- [documentation/RUNBOOK.md](documentation/RUNBOOK.md)

Дополнительно в `documentation/` теперь разведены отдельные слои:

- `ops/` — операционные документы и runtime-аудиты
- `vpn/` — VPN/Xray/3x-ui стратегия и шаблоны
- `product/` — продуктовые карты и vision-документы
- `strategy/` — roadmap и future design
- `business/` — growth / GTM / business-layer
- `ai/` — AI workflow, state и task backlog

## Технологии

Текущий стек:

- Python 3.12
- aiogram 3
- FastAPI
- SQLAlchemy + asyncpg
- PostgreSQL
- 3x-ui API
- systemd
- Jinja2
- Nginx

## Локальный запуск

```bash
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
python -m bot.main
python -m support_bot.main
python -m dashboard.main
python -m landing.main
```

## Проверки

```bash
python -m compileall bot backend dashboard support_bot
python tests/test_db.py
python tests/test_subscription.py
python tests/test_xui.py
python tests/test_manual_payments.py
python tests/test_region_integrity.py
./venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

Дополнительный safety-layer, добавленный поверх проекта:

```bash
./venv/bin/python -m unittest -q tests.test_dashboard_auth_session
./venv/bin/python -m unittest -q tests.test_payment_finalization
./venv/bin/python -m unittest -q tests.test_confirm_external_payment_record
./venv/bin/python -m unittest -q tests.test_dashboard_api_v2_contract
./venv/bin/python -m unittest -q tests.test_dashboard_api_v2_users_contract
./venv/bin/python -m unittest -q tests.test_dashboard_api_v2_support_contract
```

## Roadmap

Следующие крупные шаги по экосистеме:

- полноценный `Support Center` в веб-панели;
- более сильная система отчётов по серверам, пользователям и бюджету;
- генерация красивых управленческих отчётов;
- выделенная вкладка `Финансы` с расширенной отчётностью;
- следующий продукт внутри экосистемы Amonora.

Уже реализовано:

- автоматизации через `n8n` запущены на core host (`amonora-n8n.service`);
- автоматическая оплата через `Platega` (СБП + крипто);
- единая ссылка на подписку `client.amonoraconnect.com/<token>`;
- промокоды и подарочные подписки.

## Важные ограничения на текущий момент

- `Telegram Stars` остаются основным нативным способом оплаты внутри Telegram;
- `Platega` auto-платежи работают, но ручной контур остаётся как emergency fallback;
- смена протокола у уже созданного устройства не реализована без пересоздания;
- юридические документы уже есть, но пока находятся в промежуточной стадии и будут уточняться по мере оформления оператора.
