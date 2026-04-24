# Ревизия main bot runtime

Дата: `2026-04-25`

## Активный путь исполнения

- Точка входа главного бота: `bot/main.py`
- В `bot/main.py` диспетчер подключает только `bot.router` через `dp.include_router(main_router)`.
- Активный пользовательский runtime главного бота живёт в `bot/router.py`.
- Модульные источники UI для активного flow:
  - тексты экранов: `bot/ui/screens/user.py`
  - inline-клавиатуры: `bot/ui/keyboards/inline/user.py`
  - summary/helper-логика: `bot/services/user/summary.py`

## Что подтверждено по runtime

- `bot/main.py` не подключает `bot/handlers/*`.
- В `bot/router.py` нет `include_router(...)` для legacy handlers.
- Активный main-bot flow построен вокруг v2 callback-ов и `_send_screen(...)` / `_edit_screen(...)`.

## Дубли и shadowing в `bot/router.py`

В `bot/router.py` есть слой legacy/inline helper-ов, а ниже по файлу идёт повторный импорт модульных helper-ов из `bot/ui/*` и `bot/services/*`. Из-за этого одноимённые локальные функции/константы оказываются затенены поздним импортом.

### Подтверждённые дубли экранных helper-ов

- `_bonus_text`
- `_bonus_stats_text`
- `_screen_photo`
- `_subscription_text`
- `_renew_text`
- `_devices_page_text`
- `_device_instruction_text`
- `_device_detail_text`

### Подтверждённые дубли keyboard helper-ов

- `_agreement_keyboard`
- `_trial_keyboard`
- `_trial_ready_keyboard`
- `_trial_used_keyboard`
- `_support_keyboard`
- `_info_keyboard`
- `_info_documents_keyboard`
- `_guides_keyboard`
- `_devices_keyboard`
- `_device_guide_keyboard`
- `_main_menu_keyboard`
- `_subscription_keyboard`
- `_subscription_key_menu_keyboard`
- `_my_devices_keyboard`
- `_bonus_keyboard`
- `_bonus_stats_keyboard`
- `_bonus_promo_keyboard`
- `_bonus_gift_keyboard`
- `_renew_keyboard`
- `_renew_payment_methods_keyboard`
- `_renew_manual_payment_keyboard`
- `_renew_external_payment_keyboard`

### Подтверждённые дубли service/helper-логики

- `_load_test_user_summary`
- `_load_bonus_summary`
- `_load_pending_discount_payload`
- `_subscription_connection_uri`
- `_get_owned_test_device_for_telegram`

## Что изменено в этом проходе

- Активный бонусный текст оставлен в одном каноническом месте: `bot/ui/screens/user.py`.
- Локальные дубли `_bonus_text`, `_bonus_stats_text` и `_screen_photo` убраны из `bot/router.py`.
- Навигация `Мои устройства -> Назад` в активном runtime возвращает в экран ключа, а не в `Моя подписка`.
- `_edit_screen(...)` больше не создаёт новое сообщение как fallback для активного v2-flow и пытается обновлять текущее сообщение in-place.
- Для reply-flow добавлена обработка текста `Главное меню` / `Меню` в активном `bot/router.py`.

## Legacy-кандидаты

Следующие файлы не входят в подтверждённый путь `bot.main -> bot.router` и выглядят как старый слой главного бота:

- `bot/handlers/start.py`
- `bot/handlers/devices.py`
- `bot/handlers/tariffs.py`
- `bot/handlers/referrals.py`
- `bot/handlers/info.py`
- `bot/handlers/cabinet.py`
- `bot/handlers/protocol.py`
- `bot/handlers/support.py`

Связанный legacy UI-слой:

- `bot/keyboards/main_menu.py`
- `bot/keyboards/home.py`
- `bot/keyboards/devices.py`
- `bot/keyboards/tariffs.py`
- `bot/keyboards/referrals.py`
- `bot/keyboards/info.py`
- `bot/keyboards/protocols.py`

## Не удалять без второго прохода

- `bot/handlers/*` и `bot/keyboards/*` пока лучше считать `cleanup candidates`, а не удалять сразу.
- На них всё ещё есть внутренние импорты друг друга и отдельные тесты legacy-поведения.
- Перед физическим удалением нужен второй проход:
  - проверить ссылки из тестов;
  - проверить документацию;
  - подтвердить, что продовый runtime не использует эти модули вне `bot.main`.

## Generated / ignorable

- `bot/__pycache__`
- `bot/keyboards/__pycache__`

Это служебные артефакты интерпретатора, не источник логики и не повод для cleanup-решений.
