# TASK 117 — Control Bot UX Follow-Up Result

## Result

`@amonora_control_bot` received a focused UX cleanup pass on top of the full redesign.

The shell is now shorter, less repetitive, and more Telegram-native for operators:

- `/start` keeps only the profile block and no longer repeats the entire sections list;
- long separators were shortened to avoid mobile wrapping;
- `Статус системы` lost the noisy `ДЕТАЛЬНО` suffix;
- service rows now read as `service — 🟢 active` without duplicated leading status icons;
- the main menu no longer prioritizes a separate `Ошибки` button; events stay the main operational feed.

## Payment flow changes

- `Платежи` now stay inside Telegram and no longer expose panel deep-links;
- the payments summary screen uses `Обновить` plus direct Telegram-open buttons for reviewable requests;
- incoming manual payment events now arrive immediately with `Подтвердить / Отклонить`;
- rejection copy for the user was tightened to the simple administrator-driven wording.

## Nodes / events / auth changes

- node names are normalized for `Германия`, `Эстония`, `Дания`, `Швеция`;
- unknown region codes no longer silently reuse Germany counters in server snapshots;
- recovery/node notifications are now short and duration-based instead of multi-line host dumps;
- event and users views now prefer Telegram ID instead of leaking device/internal IDs for key issuance;
- `Авторизация` now renders as a compact sessions list and keeps only `Завершить все` for owner.

## Validation

- `python3 -m py_compile control_bot/queries.py control_bot/router.py control_bot/dispatcher.py control_bot/keyboards.py bot/manual_payments.py bot/utils/texts.py bot/utils/regions.py ops/server_watchdog.py dashboard/services.py tests/test_control_queries.py tests/test_dashboard_server_region_mapping.py`
- `./venv/bin/python -m unittest -q tests.test_control_queries tests.test_control_router tests.test_control_dispatcher tests.test_dashboard_server_region_mapping tests.test_access_reminders_triggers tests.test_bot_copy_updates`
- `git diff --check`
