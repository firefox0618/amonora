# TASK 136 — Denmark MTProto proxy rollout result

Дата: 26 марта 2026

## Что сделано

На Denmark `81.17.159.58` / `dk.amonoraconnect.com` поднят отдельный Telegram-only `MTProto` proxy через `mtg` как самостоятельный `systemd`-сервис, без замены действующего `Xray core`.

Принцип rollout:

- действующие Denmark `443/8443` профили и test listeners `9443/10443` не менялись;
- MTProto proxy вынесен в отдельный runtime path и отдельный публичный порт;
- rollout не затрагивает `@amonora_bot`, `@test_amonora_bot`, dashboard и provisioning logic;
- shared `tg://proxy` ссылка хранится и раздается вручную, не в репозитории.

## Runtime

- service: `amonora-dk-mtg.service`
- binary: `/usr/local/bin/mtg`
- config: `/etc/mtg.toml`
- public host: `dk.amonoraconnect.com`
- public host resolves to: `81.17.159.58`
- public port: `11443`
- camouflage hostname: `www.apple.com`
- pre-change backup dir: `/root/task136-denmark-mtg-prechange-20260326-023238`

Важно:

- исходный план предполагал `9443`, но live inspection показал, что на Denmark этот порт уже занят `xray` test profile;
- чтобы не ломать existing Denmark test surface, MTProto proxy вынесен на `11443`.

## Validation

- `systemctl is-active amonora-dk-mtg.service` -> `active`
- `ss -tulpn` confirms `*:11443`
- `ufw status` confirms `11443/tcp allow`
- `xray.service` stays `active`
- controlled negative scenario verified: after `systemctl stop amonora-dk-mtg.service` the Denmark `xray` listeners on `443/8443/9443/10443` stayed alive; after `systemctl start amonora-dk-mtg.service` listener `*:11443` came back
- existing Denmark listeners remain on:
  - `443`
  - `8443`
  - `9443`
  - `10443`

## Rollback

- `systemctl stop amonora-dk-mtg.service`
- `systemctl disable amonora-dk-mtg.service`
- удалить `/etc/systemd/system/amonora-dk-mtg.service`
- удалить `/etc/mtg.toml`
- удалить `/usr/local/bin/mtg`
- удалить `11443/tcp` из `ufw`

## Что не хранится в git

- shared MTProto secret
- итоговая `tg://proxy` ссылка
- operator-facing manual link format: `tg://proxy?server=dk.amonoraconnect.com&port=11443&secret=<shared_secret>`
- любые rotated replacement secrets

## Update: 29 March 2026

- the original `mtg` runtime was later replaced on the live Denmark host by the official `Telegram MTProxy` implementation because `@MTProxybot` rejected the `mtg` FakeTLS secret format and `mtg v2` has no `adtag` support;
- current live service is `amonora-dk-mtproxy.service`, with runtime files in `/etc/mtproxy/` and the same public listener `11443/tcp`;
- migration backup dir: `/root/task143-denmark-mtproxy-adtag-migration-20260329-165455`;
- the official upstream source required a local compatibility patch in `common/pid.c` on Ubuntu 24.04, because the unpatched binary asserted on high modern PIDs when `kernel.pid_max` exceeded `65535`;
- the actual promoted-channel flow is still a separate operator step: register `dk.amonoraconnect.com:11443` plus the live `32-hex` secret in `@MTProxybot`, receive the proxy tag, then add it to the service via `-P <proxy_tag>`.
