# Referral / Panel UI Cleanup Report — 2026-03-22

## Что изменено

### Бот

- кнопка `🎁 Рефералы` переименована в `🎁 Реферальная система`
- реферальный экран переведён на рублёвый Баланс
- старые приглашённые друзья переконвертированы в рубли через reconcile/backfill
- `VLESS` / `Trojan` теперь в пользовательских текстах выдают `ключ`, а не `конфиг`

### Поддержка

- support bot теперь принимает только:
  - текст
  - фото
  - видео
  - аудио
- video notes / documents / stickers / animation / voice больше не принимаются как клиентские media-вложения

### Панель управления

- новый frontend полностью живёт в `dashboard/ui`
- top-level папка `dashboard_v2` удалена
- production service renamed to `amonora-dashboard-ui.service`
- user-facing название контура закреплено как `Панель управления`

### VPN / legacy cleanup

- кодовые следы `WireGuard` удалены из активного продукта
- legacy `wireguard` inbound на Estonia удалён из `3x-ui`

## Как пользоваться

### Реферальная система

1. Открой в боте `🎁 Реферальная система`
2. Скопируй или отправь свою ссылку
3. После первой оплаты друга бот начислит `50 ₽` на Баланс
4. При оплате RUB-тарифа Баланс спишется автоматически полностью или частично

### Панель управления

1. Открой `https://amonoraconnect.com/login`
2. Введи логин и пароль
3. Получи код в `@amonora_control_bot`
4. После входа используй разделы:
   - `Обзор`
   - `Пользователи`
   - `Платежи`
   - `Поддержка`
   - `Серверы`
   - `Сервисы`
   - `Документация`

## Проверки

### Локально

- `41` автоматический тест — `OK`
- `python3 -m compileall ...` — `OK`
- `git diff --check` — `OK`

### Прод

- `amonora-dashboard-ui.service` — `active`
- `amonora-dashboard-v2.service` — `not-found`
- `dashboard/ui` production build — `OK`
- referral reconcile:
  - `users_scanned = 53`
  - `users_credited = 4`
  - `credited_rub = 250`
- точечная проверка:
  - `548589949|50|1|1`
- Estonia inbounds after cleanup:
  - `vless:443`
  - `trojan:8443`

## Backup

- pre-change backup root:
  - `/opt/amonora_bot_backup/referral-panel-cleanup-20260322-052624`

## Итог

Задача закрыта.

- реферальная система приведена к рублёвому Балансу
- старые приглашённые пользователи доначислены
- support media policy ужесточена
- Панель управления собрана в один актуальный UI-контур
- live `WireGuard` legacy removed
