# TASK 132 — Amonora test bot rollout result

Дата: 25 марта 2026

## Что сделано

Поднят отдельный admin-only Telegram bot для тестовых VPN-профилей:

- service: `amonora-test-bot.service`
- entrypoint: `python -m test_bot.main`
- token source: `AMONORA_TEST_BOT_TOKEN` в server-side `.env`

Новый бот не вмешивается в:

- `amonora-bot.service`
- обычную выдачу устройств
- платежный flow
- user-facing меню прод-бота

## Что умеет бот

Новый бот отдаёт только 4 статических test-конфига:

- Germany Android test
- Germany iPhone test
- Denmark Android test
- Denmark iPhone test

Для каждого профиля бот отправляет:

- краткое описание
- `vless://` ссылку
- QR-код

Доступ ограничен allowlist Telegram ID:

- source of truth: `AMONORA_TEST_BOT_ALLOWED_TELEGRAM_IDS`
- fallback: `ADMIN_IDS`

## Серверная часть

Перед выдачей ссылок в уже существующие test-inbound добавлены статические client UUID:

- Germany `9443`:
  - `9d75f8df-66e3-490b-aece-5a6d1ac1ed0a`
- Germany `10443`:
  - `23e52c57-d0cf-4991-9e0a-c265a39c07c8`
- Denmark `@xhttp-dk-android-test`:
  - `abc64735-5f69-45d9-b14f-353f0b134da4`
- Denmark `@xhttp-dk-ios-test`:
  - `f3426388-e8d6-4cb0-883b-425b5a68b30d`

## Валидация

- backend compile-check:
  - `python -m py_compile bot/config.py test_bot/access.py test_bot/profiles.py test_bot/router.py test_bot/main.py`
- service status:
  - `amonora-test-bot.service` -> `active`
- контроль:
  - `amonora-bot.service` остался `active`

## Ограничения

- это не public bot и не замена основного `@amonora_bot`
- это операторский test surface для controlled проверки новых VPN-профилей
- токен test-бота не должен храниться в репозитории и должен быть ротирован, если когда-либо попадал в переписку или лог
