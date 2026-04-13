# AMONORA — PRODUCT SPECS (MODULES)

Дата: 19 марта 2026

---

# 🎯 ЦЕЛЬ

> Зафиксировать продуктовые спецификации для ключевых модулей Amonora:
- функции
- логика работы
- API / backend поведение
- user flow

---

# 🧩 1. MODULE: ACCESS (VPN)

## ФУНКЦИИ
- выдача ключей (VLESS / Trojan)
- управление устройствами
- выбор региона
- продление доступа

## USER FLOW
1. пользователь → бот
2. выбрать сервер
3. получить ключ / QR
4. подключиться

## BACKEND ЛОГИКА
- create VpnClient
- sync с 3x-ui
- хранение expiry
- лимит устройств

## API
- POST /vpn/create
- POST /vpn/delete
- GET /vpn/config

---

# ⚙️ 2. MODULE: AUTOMATIONS

## ФУНКЦИИ
- Telegram bots
- обработка заявок
- автоответы
- интеграции

## USER FLOW
1. клиент пишет в бот
2. система обрабатывает
3. уведомление админу
4. сохранение данных

## BACKEND ЛОГИКА
- webhook обработка
- сценарии (flows)
- AI обработка

## API
- POST /automation/run
- POST /automation/config
- GET /automation/status

---

# 📊 3. MODULE: DATA

## ФУНКЦИИ
- парсинг сайтов
- мониторинг
- алерты

## USER FLOW
1. пользователь задаёт источник
2. система парсит
3. отправляет уведомление

## BACKEND
- cron jobs
- scraper
- хранение данных

## API
- POST /data/source
- GET /data/results

---

# 🤖 4. MODULE: AI

## ФУНКЦИИ
- ответы клиентам
- генерация текста
- анализ

## USER FLOW
1. запрос
2. AI обработка
3. ответ

## BACKEND
- OpenAI API
- prompt templates
- логирование

## API
- POST /ai/chat
- POST /ai/generate

---

# 🔗 5. ОБЩАЯ ЛОГИКА

Все модули:
- используют один user_id
- один billing
- один бот

---

# 💰 6. БИЛЛИНГ

- подписки (VPN)
- usage / услуги (automation, AI)

---

# 🧠 7. ГЛАВНАЯ ИДЕЯ

> один core — много продуктов

---

# END
