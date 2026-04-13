# TASK 134 — VPN test profile rotation round 2

Дата: 25 марта 2026
Статус: complete (pending user mobile validation)

## Контекст

Первый admin-only раунд test profiles дал такой практический результат:

- на телефоне по мобильной сети не заработал ни один профиль;
- на ПК заработали только `Germany Android` и `Germany iPhone`;
- Denmark test profiles не подтвердились как рабочие;
- live inspection показал, что Germany production держится на `VLESS + Reality + TCP` с `www.microsoft.com`, а Denmark production — на outer `Reality + TCP` и inner `XHTTP` с `www.apple.com`, путями `/api/v1/updates` и `/graphql`.

Из-за этого второй раунд должен:

- убрать первую test-четвёрку как продуктовую основу;
- пересобрать новую четверку уже на базе live-характеристик основного бота;
- не ломать production `443/8443`;
- сохранить controlled admin-only surface.

## Итоговая восьмерка

### Germany

- `Germany Mobile Android`
  - `VLESS + Reality + TCP`
  - port `9443`
  - `SNI = www.microsoft.com`
  - `fingerprint = chrome`

- `Germany Mobile iPhone`
  - `VLESS + Reality + TCP`
  - port `10443`
  - `SNI = www.microsoft.com`
  - `fingerprint = safari`

### Denmark

- `Denmark Mobile Android`
  - outer `Reality + TCP`
  - inner `XHTTP`
  - port `9443`
  - `SNI = www.apple.com`
  - path `/api/v1/updates`
  - `fingerprint = chrome`

- `Denmark Mobile iPhone`
  - outer `Reality + TCP`
  - inner `XHTTP`
  - port `10443`
  - `SNI = www.apple.com`
  - path `/graphql`
  - `fingerprint = safari`

### Estonia

- `Estonia Mobile Android VLESS`
  - `VLESS + Reality + TCP`
  - port `443`
  - `SNI = www.microsoft.com`
  - `fingerprint = chrome`

- `Estonia Mobile iPhone VLESS`
  - `VLESS + Reality + TCP`
  - port `443`
  - `SNI = www.microsoft.com`
  - `fingerprint = safari`

- `Estonia Mobile Android Trojan`
  - `Trojan + TLS`
  - port `8443`
  - `SNI = connect.amonoraconnect.com`

- `Estonia Mobile iPhone Trojan`
  - `Trojan + TLS`
  - port `8443`
  - `SNI = connect.amonoraconnect.com`

## Что сделано локально

- обновлены `test_bot/profiles.py` и `test_bot/router.py` под новую восьмерку;
- `test_bot` теперь поддерживает и `Trojan TLS` профили через `build_trojan_link_from_metadata` в `bot/utils/vless.py`;
- добавлен локальный rollout script:
  - `ops/local/rollout_vpn_test_profiles_round2_2026_03_25.py`
- добавлен smoke-test:
  - `tests/test_test_bot_profiles.py`

Локальная валидация:

- `python3 -m py_compile test_bot/profiles.py test_bot/router.py test_bot/main.py ops/local/rollout_vpn_test_profiles_round2_2026_03_25.py`
- `venv/bin/python -m unittest tests.test_test_bot_profiles`

## Что изменено live

- Germany test inbounds `9443/10443` заменены на mobile-oriented `Reality + TCP` с `www.microsoft.com`
- Denmark test profiles `9443/10443` заменены на mobile-oriented `Reality + TCP -> XHTTP` с live paths `/api/v1/updates` и `/graphql`
- Estonia полностью repurpose-нута как test-only mobile node:
  - `443` -> `VLESS + Reality + TCP`
  - `8443` -> `Trojan + TLS`
- backend test bot обновлен и после restart показывает ровно `8` новых профилей
- `amonora-bot.service` не перезапускался и не менялся

## Что проверить руками дальше

1. Android по мобильной сети:
   - Germany Mobile Android
   - Denmark Mobile Android
   - Estonia Mobile Android VLESS
   - Estonia Mobile Android Trojan
2. iPhone по мобильной сети:
   - Germany Mobile iPhone
   - Denmark Mobile iPhone
   - Estonia Mobile iPhone VLESS
   - Estonia Mobile iPhone Trojan
3. Если какой-то профиль поднимается:
   - проверить `Google`
   - проверить `YouTube`
   - проверить `Telegram text`
   - проверить `Telegram media`
