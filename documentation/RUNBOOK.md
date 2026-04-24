# RUNBOOK

## Карта сервисов

| Сервис | Как запускается | Порт | Зависимости |
|--------|----------------|------|-------------|
| **bot** (`@amonora_bot`) | `amonora-bot.service` | polling | Telegram API, backend, PostgreSQL |
| **support_bot** | `amonora-support-bot.service` | polling | Telegram API, backend, PostgreSQL |
| **control_bot** | `amonora-control-bot.service` | polling | Telegram API, backend, PostgreSQL |
| **test_bot** | `amonora-test-bot.service` | polling | Telegram API, backend, PostgreSQL |
| **dashboard** | `amonora-dashboard.service` | `127.0.0.1:8088` | backend, PostgreSQL |
| **dashboard/ui** | `amonora-dashboard-ui.service` | `127.0.0.1:3001` | dashboard API |
| **landing** | `amonora-landing.service` | через nginx | backend, PostgreSQL |
| **n8n** | `amonora-n8n.service` | `127.0.0.1:5678` | Node.js |

nginx маршрутизирует внешний трафик на внутренние порты.

## VPN-ноды

| Нода | IP | Домен | Runtime |
|------|----|-------|---------|
| Германия | `213.108.20.34` | `ffconnect.amonoraconnect.com` | 3x-ui (Docker) |
| Дания | `81.17.159.58` | `dk.amonoraconnect.com` | Xray core (standalone) |
| Эстония | `185.88.37.71` | `est.amonoraconnect.com` | x-ui / Xray |

## Быстрая диагностика

### Бот не работает
```bash
systemctl status amonora-bot.service
journalctl -u amonora-bot.service --since "1 hour ago"
```
Проверить: `BOT_TOKEN`, доступность PostgreSQL, VPN API.

### Dashboard не отвечает
```bash
curl -s http://127.0.0.1:8088/health  # или аналогичный endpoint
systemctl status amonora-dashboard.service
systemctl status amonora-dashboard-ui.service
```

### VPN-нода недоступна
```bash
# Germany (3x-ui)
curl -s http://127.0.0.1:<panel-port>/...  # через tunnel

# Denmark (Xray core)
ssh dk-host "systemctl status xray"

# Estonia
ssh ee-host "systemctl status 3x-ui"
```

## Операционные правила

- Нет изменения без backup
- Одно изменение за раз
- Без rollback-плана — опасные изменения не делать
- Старых VPN-пользователей не ломать ради нового конфига

## Backup

- Core PostgreSQL: `amonora-core-pg-backup.timer` (server-side)
- VPN-ноды: pre-change backup перед каждым изменением
- Off-host backup: подтверждён не полностью — считать частично рабочим
- Перед рискованными изменениями: явный pre-change backup

## Restore

- Restore-скрипты существуют, но хрупкие
- Наличие скриптов ≠ гарантия безопасного отката
- Dashboard-side restore readiness = `unknown` без свежего `restore-proof.json`

## Где лежат конфиги

| Что | Где |
|-----|-----|
| systemd units | `ops/systemd/` |
| nginx | `ops/nginx/` |
| env templates | `ops/env/` |
| backup scripts | `ops/backup/` |
| n8n workflows | `ops/n8n/workflows/` |

> **Примечание:** `amonora-n8n.service` и `amonora-dk-mtproxy.service` подтверждены на production, но unit-файлы ещё не добавлены в `ops/systemd/` (настроены напрямую на серверах).

## Локальный запуск

```bash
# Установка зависимостей
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt

# Запуск сервисов (каждый в отдельном терминале)
python -m bot.main          # клиентский бот
python -m support_bot.main  # бот поддержки
python -m control_bot.main  # бот управления
python -m dashboard.main    # backend админки
python -m landing.main     # публичный сайт
```

## Проверки

```bash
# Компиляция всех модулей
python -m compileall bot backend dashboard support_bot

# Все тесты
./venv/bin/python -m unittest discover -s tests -p 'test_*.py'

# Отдельные группы тестов
./venv/bin/python -m unittest -q tests.test_dashboard_auth_session
./venv/bin/python -m unittest -q tests.test_payment_finalization
./venv/bin/python -m unittest -q tests.test_confirm_external_payment_record
```
