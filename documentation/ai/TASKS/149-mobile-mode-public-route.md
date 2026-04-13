# TASK 149 — Mobile mode public route

## Context

`Мобильный` режим уже имел runtime support через `MOBILE_MODE_OVERRIDE_LINK_DE` / `MOBILE_MODE_OVERRIDE_LINK_DK`, но оставался admin-only и в user-facing copy выглядел как временная заглушка "скоро появится".

Пользовательский запрос:

- открыть `Мобильный` режим как рабочий маршрут для Germany и Denmark;
- сохранить runtime delivery через shared import-link из env, без коммита самого ключа в репозиторий;
- переупаковать product copy так, чтобы пользователю был понятен сценарий сетей с ограниченным набором доступных направлений, но без терминов вроде "white list".

## Scope

- `bot/utils/modes.py`
- `tests/test_bot_copy_updates.py`
- product docs for current feature/public-state status
- production env update for `MOBILE_MODE_OVERRIDE_LINK_DE` and `MOBILE_MODE_OVERRIDE_LINK_DK`

## Acceptance Criteria

- обычный пользователь видит `Мобильный` режим как доступный в DE/DK flows;
- mode selection no longer returns the "скоро появится" placeholder for ordinary users;
- shared mobile link stays runtime-only and is not committed into git;
- user-facing descriptions explain the route purpose without technical whitelist wording.
