# Denmark Golden Node Report — 2026-03-21

## Summary

Готово:

- `Denmark` закреплена как текущая golden anti-DPI нода;
- `Germany` сохранена как стабильный compatibility route;
- `Estonia` сохранена как reserve/testing нода;
- fleetwide baseline применён без опасной миграции `DE/EE` на новый transport stack;
- официальные client packs и MTU policy опубликованы в knowledge.

## Node posture

### Denmark

- runtime: standalone `Xray core`
- camouflage: `www.apple.com`
- primary:
  - `443`
  - `XHTTP packet-up`
  - `/api/v1/updates`
- reserve:
  - `8443`
  - `XHTTP packet-up`
  - `/graphql`
- DNS:
  - `https+local://cloudflare-dns.com/dns-query`
  - `https+local://dns.sb/dns-query`
  - `localhost`
- Reality fingerprint:
  - `chrome`
- logging:
  - `none`
- SSH automation path:
  - explicit `22/tcp` allowlist from core host `46.21.81.186`
  - generic `ufw limit 22/tcp` remains for everyone else

### Germany

- runtime: `3x-ui`
- role: stable compatibility route
- baseline:
  - `bbr`
  - `tcp_fastopen = 3`
  - `tcp_mtu_probing = 1`
  - enlarged buffers
  - `nofile = 65535`
  - `sniffing.enabled = true` on proxy inbounds through `x-ui.db`
  - `2053/2096` shielded

### Estonia

- runtime: `3x-ui`
- role: reserve/testing
- user-facing posture:
  - hidden from normal route choice
- baseline:
  - `bbr`
  - `tcp_fastopen = 3`
  - `tcp_mtu_probing = 1`
  - enlarged buffers
  - `nofile = 65535`
  - `sniffing.enabled = true` on proxy inbounds through `x-ui.db`
  - `2053/2096` shielded

## Client artifacts

Published official pack set:

- `v2rayNG`
- `Nekoray`
- `Streisand`

Modes:

- `Recommended split-tunnel`
- `Full-tunnel fallback`

MTU policy:

- default: `1400`
- fallback: `1420`

Formats:

- JSON import artifacts
- QR-code references for mobile onboarding
- text snippets with MTU and routing guidance

## Completion Table

| Пункт | Статус | Что сделано | Доказательство |
|---|---|---|---|
| Backup layer before hardening | Выполнено | Для `DK/DE` снят explicit pre-change snapshot; для `EE` подтверждён существующий `3x-ui` backup layer до прохода | `DK/DE: /root/amonora-golden-node-prechange-20260321-061645*`; `EE: /opt/3x-ui/backups/x-ui.db.20260316-195700`, `x-ui.db.20260317-220759`, `config.json.20260317-220759` |
| Post-change rollback snapshots | Выполнено | Сняты свежие post-change snapshots на всех нодах | `DK: /root/amonora-golden-node-postchange-20260321-053834*`; `DE: /root/amonora-golden-node-postchange-20260321-053115*`; `EE: /root/amonora-golden-node-postchange-20260321-053206*` |
| Denmark primary profile | Выполнено | `443` -> outer `Reality` -> inner `@xhttp-dk-primary` -> `/api/v1/updates` -> `packet-up` | `config.json` + `amonora_dk_meta.json`, `xray run -test`, `systemctl is-active xray = active` |
| Denmark reserve profile | Выполнено | `8443` -> outer `Reality` -> inner `@xhttp-dk-reserve` -> `/graphql` -> `packet-up` | live `config.json` verify on `amonora-dk-1` |
| Denmark DNS and logging policy | Выполнено | DoH/local upstreams, `loglevel = none` | live `config.json` verify on `amonora-dk-1` |
| Fleet sysctl baseline | Выполнено | `bbr`, `tcp_fastopen = 3`, `tcp_mtu_probing = 1`, `rmem/wmem = 33554432`, `nofile = 65535` | live `sysctl` + limits checks on `DK/DE/EE` |
| Firewall normalization | Выполнено | `22/tcp limit`, `443/tcp`, `8443/tcp`; лишние public rules убраны | live `ufw status verbose` on `DK/DE/EE` |
| Panel shielding on DE/EE | Выполнено | `2053/2096` оставлены только для локальной панели и закрыты снаружи | `amonora-xui-shield.service = active`; external `/dev/tcp` to `2053/2096` -> `BLOCKED` |
| Persistence-safe torrent block | Выполнено | `bittorrent -> blocked` сохранён, а detection на `DE/EE` усилился через `sniffing.enabled` в `x-ui.db` | live generated runtime + DB verify on `DE/EE`; `routing.rules` contain `protocol = bittorrent` |
| Client packs | Выполнено | Опубликованы official JSON artifacts для `v2rayNG`, `Nekoray`, `Streisand` | `documentation/vpn/client-packs/*` + JSON parsing locally |
| MTU policy | Выполнено | `1400` default и `1420` fallback встроены в packs/docs | `CLIENT_PACK_POLICY.md`, `VPN_CONFIG_STRATEGY.md`, `supporting/user-guide.md` |
| Knowledge publication | Выполнено | Baseline docs, client-pack policy и этот operator report добавлены в knowledge/manifest | `documentation/manifest.json` updated |

## Operational note

Этот проход сознательно **не** делал fleetwide migration `Germany/Estonia` на standalone `Xray core`.

Текущая безопасная модель:

- `Denmark` = fast modern route
- `Germany` = stable compatibility route
- `Estonia` = reserve/testing
