# Операционный runbook Amonora

> Supporting historical runbook. Use [RUNBOOK.md](/home/dextrmed/projects/amonora_bot/documentation/RUNBOOK.md) and the `documentation/ops/` layer as canonical current-state operational docs first.

## 1. Актуальная схема стран

- `de` — Германия — основная VPN-нода — `ffconnect.amonoraconnect.com`
- `dk` — Дания — основная modern anti-DPI нода — `dk.amonoraconnect.com`

Source of truth по региону должен определять:

- `country_code`
- `country_name`
- `vpn_host`
- `panel_url`
- импортируемое имя подключения

## 2. Tunnel и panel checks

На backend должны быть доступны:

- `XUI_URL_DE=http://127.0.0.1:12053`

Быстрая проверка:

```bash
systemctl status amonora-xui-tunnel
curl -I http://127.0.0.1:12053/login
```

Если tunnel сломан:

1. Проверить `ssh` до нужной VPN-ноды.
2. Проверить ключ и `known_hosts`.
3. Перезапустить tunnel-сервис.
4. Снова проверить `tests/test_region_integrity.py`.

## 3. Проверка активных VPN-регионов

Перед изменениями в VPN-контуре:

```bash
python tests/test_region_integrity.py
```

Скрипт должен подтвердить:

- `DE` panel login проходит
- `DK` runtime health check проходит
- `EE` помечен как retired region, а не как активная panel-backed нода

## 4. Ручные платежи

Рабочий боевой контур:

- `Telegram Stars`
- `Ручная СБП`
- `Ручная крипта`

Auto `Crypto Bot` остаётся в коде за feature flag и не считается основным боевым методом.

### Статусы ручной заявки

- `awaiting_user_payment`
- `awaiting_admin_review`
- `confirmed`
- `rejected`
- `expired`
- `cancelled`

### Пользовательский flow

1. Пользователь выбирает тариф.
2. Выбирает `СБП` или `Крипта`.
3. Получает реквизиты и номер заявки.
4. После оплаты нажимает `Я оплатил`.
5. Заявка уходит в `awaiting_admin_review`.

### Подтверждение администратором

Подтверждать можно:

- в `@amonora_control_bot` через `/payments`
- в дашборде во вкладке `Платежи`

После `confirm`:

- запись помечается `confirmed`
- доступ продлевается
- срок синхронизируется в VPN
- действие пишется в аудит

После `reject`:

- запись помечается `rejected`
- пользователю уходит уведомление

## 5. Backup перед live-миграциями

Перед reconcile, миграцией БД или ручной правкой панелей обязательно сделать:

### PostgreSQL

```bash
pg_dump -Fc -h 127.0.0.1 -U amonora -d amonora_db -f /opt/amonora_bot/backups/amonora_$(date +%Y%m%d_%H%M%S).dump
```

### 3x-ui Германия

```bash
ssh root@213.108.20.34 "cp /opt/3x-ui/db/x-ui.db /opt/3x-ui/backups/x-ui.db.$(date +%Y%m%d_%H%M%S).bak"
```

### 3x-ui Эстония

```bash
ssh root@185.88.37.71 "cp /opt/3x-ui/db/x-ui.db /opt/3x-ui/backups/x-ui.db.$(date +%Y%m%d_%H%M%S).bak"
```

## 6. Reconcile устройств

Проверка без изменений:

```bash
python reconcile_vpn_regions.py
```

Применение фиксов:

```bash
python reconcile_vpn_regions.py --apply
```

Восстановление missing panel-клиентов для активного доступа:

```bash
python reconcile_vpn_regions.py --repair-missing-remote
```

Что делает reconcile:

- сверяет `vpn_clients.client_data.country_code` с фактическим местом клиента в panel
- нормализует legacy alias `nl -> de`
- восстанавливает region snapshot в metadata
- обновляет `inbound_id`, если он найден фактически в панели
- не считает текущие runtime-managed профили (`AmneziaWG` / `xray_core`) “missing in panel”
- по явному `--repair-missing-remote` умеет пересоздать missing `xui`-клиента для пользователя с ещё активным доступом

## 7. Recovery playbook

Дополнительный локальный drill-рецепт:

- `documentation/ops/LOCAL_RESTORE_RECIPE.md` — как проверить локально PostgreSQL dump и `x-ui.db` через Docker / SQLite без изменений на серверах
- `C:\Users\Skyfal\Scripts\amonora\restore_core_pg_local.ps1` — one-click локальный PostgreSQL restore drill через временный Docker `postgres:16`

### Откат ручной заявки

Если ошибочно подтвердили ручной платёж:

1. Зафиксировать `payment_record.id`
2. Проверить, был ли продлён доступ
3. При необходимости вручную скорректировать срок доступа пользователя
4. Оставить аудит-комментарий в дашборде или internal log

### Откат reconcile

1. Восстановить дамп PostgreSQL
2. При необходимости вернуть `x-ui.db` из backup на конкретной ноде
3. Перезапустить panel / backend tunnel
4. Снова прогнать `tests/test_region_integrity.py`

### Восстановление тикетов поддержки

Тикеты уже лежат в PostgreSQL, поэтому для восстановления используется общий backup БД.

## 8. Ежедневный smoke-check

```bash
systemctl is-active amonora-bot
systemctl is-active amonora-support-bot
systemctl is-active amonora-control-bot
systemctl is-active amonora-dashboard
systemctl is-active amonora-landing
systemctl is-active amonora-xui-tunnel
systemctl is-active amonora-xui-tunnel-ee
python tests/test_region_integrity.py
```

Плюс руками:

1. Открыть сайт
2. Открыть дашборд
3. Проверить `/start` в основном боте
4. Проверить `/start` в support-боте
5. Проверить `/start` в `@amonora_control_bot`
6. Создать тестовую manual-заявку
7. Подтвердить и отклонить заявку через dashboard / `Amonora Control`
