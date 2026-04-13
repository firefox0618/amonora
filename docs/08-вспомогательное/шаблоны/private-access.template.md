# 🔐 Приватные доступы (Шаблон)

> ⚠️ **ВАЖНО:** Этот файл — только шаблон.  
> Реальные данные для доступа **НЕ должны** храниться в репозитории.  
> Скопируйте этот файл как `PRIVATE_ACCESS.md` (вне репозитория) и заполните актуальными данными.

---

## 📋 Как использовать этот шаблон

1. Скопируйте файл в безопасное место (не в репозиторий):
   ```bash
   cp docs/08-вспомогательное/шаблоны/private-access.template.md ~/secure/PRIVATE_ACCESS.md
   ```

2. Заполните реальными данными

3. Убедитесь, что файл добавлен в `.gitignore`

4. Храните в зашифрованном виде (например, в менеджере паролей)

---

## 🔑 Telegram-боты

| Бот | Токен | Доступы |
|-----|-------|---------|
| @amonora_bot | `BOT_TOKEN=<токен>` | ADMIN_IDS=<id через запятую> |
| @amonora_support_bot | `SUPPORT_BOT_TOKEN=<токен>` | SUPPORT_ADMIN_IDS=<id> |
| @amonora_control_bot | `AMONORA_CONTROL_BOT_TOKEN=<токен>` | AMONORA_CONTROL_OWNER_IDS=<id> |
| @test_amonora_bot | `AMONORA_TEST_BOT_TOKEN=<токен>` | AMONORA_TEST_BOT_ALLOWED_TELEGRAM_IDS=<id> |

---

## 🗄️ База данных

| Параметр | Значение |
|----------|----------|
| Host | `DB_HOST=` |
| Port | `DB_PORT=5432` |
| Database | `DB_NAME=amonora_db` |
| User | `DB_USER=amonora` |
| Password | `DB_PASS=` |
| Connection String | `postgresql+asyncpg://user:pass@host:port/dbname` |

---

## 🖥️ Dashboard

| Роль | Логин | Пароль |
|------|-------|--------|
| Владелец | `rudolf` | `DASHBOARD_OWNER_PASSWORD=` |
| Технарь | `ruslan` | `DASHBOARD_TECH_PASSWORD=` |
| Поддержка | `muradym` | `DASHBOARD_SUPPORT_PASSWORD=` |

**URL:** Внутренний адрес (порт 8088)  
**Сессия:** 24 часа (`DASHBOARD_SESSION_HOURS=24`)

---

## 🌐 VPN-ноды

### Германия (DE) — 3x-ui

| Параметр | Значение |
|----------|----------|
| URL | `XUI_URL_DE=` |
| Username | `XUI_USERNAME=` |
| Password | `XUI_PASSWORD=` |
| Порт | 12053 |

### Дания (DK) — Xray Core

| Параметр | Значение |
|----------|----------|
| SSH Host | `XRAY_CORE_DK_SSH_HOST=81.17.159.58` |
| SSH Port | `XRAY_CORE_DK_SSH_PORT=22` |
| SSH User | `XRAY_CORE_DK_SSH_USER=root` |
| SSH Key | `XRAY_CORE_DK_SSH_KEY_PATH=` |
| Config Path | `/usr/local/etc/xray/config.json` |

---

## 💳 Платёжные системы

### Platega (SBP)

| Параметр | Значение |
|----------|----------|
| Merchant ID | `PLATEGA_MERCHANT_ID=` |
| Secret Key | `PLATEGA_SECRET_KEY=` |
| Webhook Secret | `PLATEGA_WEBHOOK_SECRET=` |
| Base URL | `https://app.platega.io` |

### Crypto Pay

| Параметр | Значение |
|----------|----------|
| API Token | `CRYPTO_PAY_API_TOKEN=` |
| Webhook Secret | `CRYPTO_PAY_WEBHOOK_SECRET=` |
| Base URL | `https://pay.crypt.bot/api` |
| Accepted Assets | USDT, TON |

### Telegram Stars

| Параметр | Значение |
|----------|----------|
| Provider Token | `STARS_PROVIDER_TOKEN=` |
| Currency | XTR |

---

## 📊 Grafana

| Параметр | Значение |
|----------|----------|
| URL | Внутренний адрес (порт 3000) |
| Login | `admin` |
| Password | `GRAFANA_ADMIN_PASSWORD=` |
| DB Connection | См. `ops/grafana/provisioning/datasources/` |

---

## 🤖 n8n (Автоматизация)

| Параметр | Значение |
|----------|----------|
| URL | Внутренний адрес (порт 5678) |
| Workflows | `ops/n8n/workflows/` |

---

## 📧 OpenAI (Генерация контента)

| Параметр | Значение |
|----------|----------|
| API Key | `OPENAI_API_KEY=` |
| Model | `gpt-4.1-mini` |

---

## 🔗 Вебхуки

| Сервис | Secret |
|--------|--------|
| Channel Webhook | `AMONORA_INTERNAL_CHANNEL_WEBHOOK_SECRET=` |
| Grafana Alerts | `AMONORA_GRAFANA_ALERTS_WEBHOOK_SECRET=` |
| Referral Push | `REFERRAL_PUSH_WEBHOOK_TOKEN=` |

---

## 📱 Telegram-канал

| Параметр | Значение |
|----------|----------|
| Channel ID | `CHANNEL_ID=` |
| Post Hour | 12 (UTC) |

---

## 🌍 VPN-хосты

| Регион | Хост | Endpoint |
|--------|------|----------|
| DE | `ffconnect.amonoraconnect.com` | `ffconnect.amonoraconnect.com:51820` |
| DK | `dk.amonoraconnect.com` | (настраивается) |
| EE | `est.amonoraconnect.com` | `connect.amonoraconnect.com:51820` |

---

## 📞 Контакты команды

| Роль | Telegram | Ответственность |
|------|----------|-----------------|
| Владелец | @firefox0618 | Стратегия, финансы |
| Технарь | (см. доступы) | Инфраструктура, код |
| Поддержка | (см. доступы) | Тикеты, клиенты |

---

## 🔒 Рекомендации по безопасности

1. **Хранение секретов:**
   - Используйте менеджер паролей (1Password, Bitwarden)
   - Никогда не храните секреты в коде или репозитории
   - Регулярно ротируйте токены (раз в 90 дней)

2. **Доступы:**
   - Принцип минимальных привилегий
   - Двухфакторная аутентификация везде, где возможно
   - Ведите журнал выданных доступов

3. **Мониторинг:**
   - Настройте алерты на подозрительную активность
   - Проверяйте логи доступа еженедельно
   - Автоматически блокируйте после 5 неудачных попыток

---

**Версия шаблона:** 1.0  
**Последнее обновление:** Апрель 2025  
**Статус:** ⚠️ Шаблон (требует заполнения)
