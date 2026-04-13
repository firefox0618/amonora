# Denmark Golden Node Baseline

## Purpose

This document captures the current golden-node policy for Denmark and the safe fleet baseline shared across the active VPN nodes.

The goal is explicit:

- `Denmark` is the primary anti-DPI node;
- `Germany` remains the compatibility route;
- `Estonia` remains reserve/testing and is not user-facing;
- legacy `3x-ui` regions are hardened without rewriting their transport model.

## Current node posture

### Denmark

- provider type: `xray_core`
- runtime source of truth:
  - `/usr/local/etc/xray/config.json`
  - `/usr/local/etc/xray/amonora_dk_meta.json`
- product posture:
  - fast modern route
  - normal public route alongside Germany

### Germany

- provider type: `xui`
- runtime source of truth:
  - `/opt/3x-ui/db/x-ui.db`
  - generated runtime inside the `3x-ui` container
- product posture:
  - stable compatibility route

### Estonia

- provider type: `xui`
- runtime source of truth:
  - `/opt/3x-ui/db/x-ui.db`
  - generated runtime inside the `3x-ui` container
- product posture:
  - reserve/testing only
  - hidden from normal user-facing selection

## Denmark golden profile

### Primary profile

- public port: `443/tcp`
- transport: `VLESS + Reality + XHTTP`
- camouflage target: `www.apple.com`
- path: `/api/v1/updates`
- XHTTP mode: `packet-up`
- ALPN policy:
  - `h3`
  - `h2`
  - `http/1.1`
- intent:
  - prefer modern mobile-friendly transport
  - keep practical compatibility fallback inside the same profile family

### Reserve profile

- public port: `8443/tcp`
- transport: `VLESS + Reality + XHTTP`
- camouflage family: `www.apple.com`
- path: `/graphql`
- XHTTP mode: `packet-up`
- ALPN policy:
  - `h2`
  - `http/1.1`
- intent:
  - reserve path when primary H3-preferred profile is unstable on a carrier or client build

### Denmark runtime policy

- `loglevel = none`
- DNS upstreams:
  - `https+local://cloudflare-dns.com/dns-query`
  - `https+local://dns.sb/dns-query`
  - `localhost`
- default Reality fingerprint: `chrome`
- explicit Reality metadata is stored in `amonora_dk_meta.json`
- operationally, the public `443/8443` listeners are `Reality` wrappers that fallback into inner `@xhttp-dk-primary` / `@xhttp-dk-reserve` inbounds; validation should inspect both the outer and inner layers
- Telegram-only `MTProto` proxy, если он поднят для ручной раздачи, должен жить как отдельный сервис через `mtg` и отдельный публичный порт, а не как часть `Xray` listeners
- the meta file must preserve:
  - active profile
  - primary profile data
  - reserve profile data
  - distinct `shortId` values for primary and reserve profiles
  - usable client-side public key field
  - MTU recommendations
  - compatibility fallback region
  - DNS upstream policy

## Fleet-wide safe baseline

The following baseline applies to `Denmark`, `Germany`, and `Estonia`:

- `BBR` enabled
- `TCP Fast Open` enabled and verified
- enlarged socket buffers for VPN traffic
- `nofile` baseline documented and enforced at host/runtime level
- firewall policy normalized
- BitTorrent blocked through Xray routing

## Torrent-block policy

### Denmark

Torrent traffic is blocked directly in standalone `Xray core` routing.

### Germany and Estonia

Torrent blocking must stay persistence-safe for `3x-ui`.

The accepted mechanism is:

- keep the existing `blocked` outbound rule for `protocol = bittorrent`;
- make sure `sniffing.enabled = true` on user-facing inbounds through `x-ui.db`, not by hand-editing generated runtime JSON;
- restart or regenerate `3x-ui` runtime after the DB-side change.

Direct ad-hoc editing of generated `config.json` is not accepted as the primary persistence layer.

## Firewall policy

### Public ports

- `22/tcp`
- `443/tcp`
- `8443/tcp` only where intentionally used
- extra Denmark-only service ports must быть отдельными и не конфликтовать с `Xray`; текущий MTProto rollout использует `11443/tcp`

### Extra rules

- `22/tcp` should use rate limiting
- `Denmark` must keep an explicit `22/tcp` allowlist for the core host (`46.21.81.186`) ahead of the generic rate-limit rule, otherwise rapid create/repair/delete automation bursts can be rejected
- public `3x-ui` panel ports must stay shielded from the internet
- `8443/tcp` remains intentionally open on `Germany` and `Estonia` while active Trojan compatibility inbounds still exist there
- if `2053` / `2096` still listen locally for panel needs, they must remain blocked from external access

## MTU policy

For mobile-heavy client paths:

- default recommendation: `1400`
- fallback recommendation: `1420`

Important:

- `1500` is not the recommended default for mobile networks in this product policy
- if a client can store MTU inside the profile or TUN settings, use `1400`
- if the client cannot import MTU from a profile, MTU must appear in the import instructions

## Client pack policy

Official packs are described in:

- `documentation/vpn/CLIENT_PACK_POLICY.md`
- `documentation/vpn/client-packs/*`

Policy summary:

- `Denmark` is preferred for compatible clients
- `Germany` remains the fallback profile for compatibility issues
- `Estonia` is not part of normal user-facing packs
- client packs include JSON for import, QR-code references for mobile operators, and text snippets with MTU and routing rules

## Validation checklist

### Denmark runtime

- `xray run -test`
- `systemctl is-active xray`
- `ss -tulpn`
- meta/config alignment check

### Fleet baseline

- `sysctl` values persist after reload/reboot
- torrent-block is active on `DK/DE/EE`
- `2053/2096` are not publicly reachable
- firewall shows only intended public routes

### Client-side policy

- split-tunnel pack:
  - Russian/domestic resources direct
  - blocked/global resources through VPN
- full-tunnel pack:
  - all traffic through VPN
- MTU guidance present for supported client packs

## Rollback rule

Every hardening change requires:

- pre-change backup archive
- runtime snapshot
- explicit note of the rollback path in the task result

For Estonia in this pass, the rollback evidence combines:

- the pre-existing `3x-ui` backup layer in `/opt/3x-ui/backups`
- the explicit post-change snapshot captured after the hardening pass

Do not overwrite the last known-good runtime without backup evidence.
