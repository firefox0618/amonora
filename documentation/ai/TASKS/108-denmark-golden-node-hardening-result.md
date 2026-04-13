# TASK 108 — Denmark Golden Node Hardening and Safe Fleet Baseline Result

## Result
Completed.

Denmark is now the current golden anti-DPI node, while Germany and Estonia stay on their existing `3x-ui` control plane with a safe shared baseline instead of an unsafe fleetwide transport migration.

## What changed

- Denmark runtime was hardened as a two-profile `Reality + XHTTP` node:
  - primary `443` -> `@xhttp-dk-primary` -> `/api/v1/updates` -> `packet-up`
  - reserve `8443` -> `@xhttp-dk-reserve` -> `/graphql` -> `packet-up`
  - `www.apple.com` camouflage
  - `fingerprint = chrome`
  - `loglevel = none`
  - DoH/local DNS upstreams (`cloudflare-dns.com`, `dns.sb`, `localhost`)
  - explicit `22/tcp` allowlist for core host `46.21.81.186` ahead of the generic `ufw limit` rule, so rapid provider create/repair/delete bursts do not trip the SSH rate-limit
- Denmark metadata now explicitly preserves:
  - active profile
  - primary/reserve profile data
  - distinct primary/reserve `shortId` values
  - MTU defaults
  - compatibility fallback region
  - usable client-side public key field
- Germany and Estonia received a safe fleet baseline without transport migration:
  - `bbr`
  - `tcp_fastopen = 3`
  - `tcp_mtu_probing = 1`
  - larger socket buffers
  - `nofile = 65535`
  - `22/tcp` under `ufw limit`
  - public panel ports `2053/2096` shielded from the internet
- `3x-ui`-backed proxy inbounds on Germany and Estonia now keep `sniffing.enabled = true` through `x-ui.db`, so the existing `bittorrent -> blocked` routing rule remains persistence-safe.
- Official client routing artifacts were published for:
  - `v2rayNG`
  - `Nekoray`
  - `Streisand`
- Pack formats are now documented as:
  - JSON import artifacts
  - QR-code references for mobile onboarding
  - text snippets with MTU and routing guidance
- MTU policy is now part of the official deliverable:
  - `1400` default
  - `1420` troubleshooting fallback

## Backup and rollback evidence

### Denmark

- pre-change:
  - `/root/amonora-golden-node-prechange-20260321-061645`
  - `/root/amonora-golden-node-prechange-20260321-061645.tgz`
- post-change:
  - `/root/amonora-golden-node-postchange-20260321-053834`
  - `/root/amonora-golden-node-postchange-20260321-053834.tgz`

### Germany

- pre-change:
  - `/root/amonora-golden-node-prechange-20260321-061645`
  - `/root/amonora-golden-node-prechange-20260321-061645.tgz`
- post-change:
  - `/root/amonora-golden-node-postchange-20260321-053115`
  - `/root/amonora-golden-node-postchange-20260321-053115.tgz`

### Estonia

- pre-existing backup layer before the pass:
  - `/opt/3x-ui/backups/x-ui.db.20260316-195700`
  - `/opt/3x-ui/backups/x-ui.db.20260317-220759`
  - `/opt/3x-ui/backups/config.json.20260317-220759`
- explicit post-change snapshot:
  - `/root/amonora-golden-node-postchange-20260321-053206`
  - `/root/amonora-golden-node-postchange-20260321-053206.tgz`

## Validation

### Local

- `./venv/bin/python -m unittest -q tests.test_denmark_vpn_provisioning`
- `python3 -m json.tool documentation/vpn/client-packs/v2rayng-split-tunnel.json`
- `python3 -m json.tool documentation/vpn/client-packs/v2rayng-full-tunnel.json`
- `python3 -m json.tool documentation/vpn/client-packs/nekoray-split-tunnel.json`
- `python3 -m json.tool documentation/vpn/client-packs/nekoray-full-tunnel.json`
- `python3 -m json.tool documentation/vpn/client-packs/streisand-split-tunnel.json`
- `python3 -m json.tool documentation/vpn/client-packs/streisand-full-tunnel.json`
- `git diff --check`

### Live runtime

- Denmark:
  - `xray run -test -config /usr/local/etc/xray/config.json` -> `Configuration OK`
  - `systemctl is-active xray` -> `active`
  - `ss -tulpn` confirms `443` and `8443`
  - meta/config match the primary and reserve profiles
  - live dashboard-service smoke confirms Denmark VLESS `create` and `delete` both work after the SSH allowlist adjustment
- Germany:
  - `amonora-xui-shield.service` -> `active`
  - `x-ui.db` and generated runtime both show proxy `sniffing.enabled = true`
  - `routing.rules` still contain `protocol = bittorrent -> blocked`
  - `ufw` exposes only `22/tcp limit`, `443/tcp`, `8443/tcp`
- Estonia:
  - `amonora-xui-shield.service` -> `active`
  - `x-ui.db` and generated runtime show proxy `sniffing.enabled = true`
  - `routing.rules` still contain `protocol = bittorrent -> blocked`
  - `ufw` exposes only `22/tcp limit`, `443/tcp`, `8443/tcp`
  - existing `51820` listener stays internal to the node policy and is not opened in `ufw`
- external panel shielding:
  - `/dev/tcp/<DE|EE>/2053` -> `BLOCKED`
  - `/dev/tcp/<DE|EE>/2096` -> `BLOCKED`

## Deliverables

- `documentation/vpn/DENMARK_GOLDEN_NODE_BASELINE.md`
- `documentation/vpn/CLIENT_PACK_POLICY.md`
- `documentation/vpn/client-packs/*`
- `documentation/ops/DENMARK_GOLDEN_NODE_REPORT_2026-03-21.md`
- updated `RUNBOOK.md`, `FEATURES.md`, `STATE.md`, `manifest.json`, `supporting/user-guide.md`, and `VPN_CONFIG_STRATEGY.md`
