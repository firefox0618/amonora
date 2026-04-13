# TASK 131 — VPN test profiles Android/iPhone rollout result

Дата: 25 марта 2026

## Что сделано

Без замены действующих пользовательских профилей добавлены новые admin-only test modes на Germany и Denmark.

Принцип rollout:

- старые `443/8443` оставлены без изменения;
- новые тестовые профили вынесены на отдельные публичные порты `9443` и `10443`;
- перед изменениями сняты pre-change backup;
- rollout оформлен в воспроизводимый ops-скрипт:
  - `ops/local/rollout_vpn_test_profiles_2026_03_25.py`

## Germany

Runtime:

- `3x-ui` в Docker
- persistence layer: `/opt/3x-ui/db/x-ui.db`

Добавлены новые inbound:

- `amonora-test-android-tcp`
  - port: `9443`
  - transport: `VLESS + Reality + TCP`
  - SNI / target: `2gis.ru`
  - fingerprint: `chrome`
- `amonora-test-iphone-tcp`
  - port: `10443`
  - transport: `VLESS + Reality + TCP`
  - SNI / target: `vk.com`
  - fingerprint: `safari`

Backup evidence:

- latest confirmed pre-change DB backup:
  - `/opt/3x-ui/backups/x-ui.db.20260325-164806.bak`

Validation:

- live listeners confirmed on:
  - `443`
  - `8443`
  - `9443`
  - `10443`

## Denmark

Runtime:

- standalone `Xray core`
- source of truth:
  - `/usr/local/etc/xray/config.json`
  - `/usr/local/etc/xray/amonora_dk_meta.json`

Добавлены новые test profiles:

- `android_test`
  - public port: `9443`
  - outer transport: `Reality + TCP`
  - inner transport: `XHTTP`
  - path: `/api/v2/android-sync`
  - camouflage family: `www.apple.com`
  - fingerprint: `chrome`
- `ios_test`
  - public port: `10443`
  - outer transport: `Reality + TCP`
  - inner transport: `XHTTP`
  - path: `/api/v2/ios-sync`
  - camouflage family: `www.apple.com`
  - fingerprint: `safari`

Inner tags:

- `@xhttp-dk-android-test`
- `@xhttp-dk-ios-test`

Validation:

- `xray` active after rollout
- live listeners confirmed on:
  - `443`
  - `8443`
  - `9443`
  - `10443`
- `amonora_dk_meta.json` contains:
  - `profiles.android_test`
  - `profiles.ios_test`

## Что не менялось

- действующие Germany `443` / `8443` профили не заменялись;
- действующие Denmark `primary` / `reserve` профили не заменялись;
- existing user links не перевыпускались;
- bot provisioning logic не переводилась на новые admin-only test modes.

## Что проверить руками дальше

- Android на Germany `9443`
- iPhone на Germany `10443`
- Android на Denmark `9443`
- iPhone на Denmark `10443`
- повторный DPI-прогон по тем же сценариям, что уже использовались для кабеля и hotspot

## Риск/ограничение

- Germany rollout потребовал controlled restart контейнера `3x-ui`;
- Denmark rollout потребовал restart `xray`;
- это не миграция массовых пользователей, а параллельный controlled test rollout для админов.
