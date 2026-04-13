# TASK 139 — configurable key anti-sharing and device technical info

## Status
Completed

## Goal
Move key anti-sharing from a hardcoded `1 IP` assumption to a configurable limit and surface device technical data in the admin panel when that data is available.

## Scope
- `bot/config.py`
- `bot/vpn_api.py`
- `ops/xray_single_ip_enforcer.py`
- `ops/systemd/amonora-dk-single-ip-enforcer.service`
- `dashboard/services.py`
- `dashboard/ui`
- focused Python tests

## What changed
- `VPN_MAX_DEVICES_PER_KEY` now drives `3x-ui limitIp` for Germany/Estonia instead of a hardcoded `1`;
- Denmark `xray_core` anti-sharing now keeps up to `N` leased IPs per key, supports a per-key whitelist JSON file, and records soft-limit violations without deleting the key;
- Denmark enforcer defaults are now explicit in the shipped systemd unit (`--max-devices`, `--lease-seconds`, `--whitelist-file`, `--soft-limit-warnings`);
- dashboard user detail now exposes a stable `technical` payload per device with available OS/model/MAC/IP/provider/transport/profile/anti-sharing fields, while preserving the old raw `metadata` block.

## Constraints
- no fake claims of physical hardware binding;
- no destructive removal of active keys as the primary anti-sharing reaction;
- preserve the existing provisioning boundary: `3x-ui` where available, external enforcement only for `xray_core`.

## Acceptance criteria
- future `x-ui` keys inherit the configured `limitIp` automatically;
- future Denmark keys inherit the same effective limit through the lease worker;
- a per-key whitelist can allow extra Denmark IPs without consuming a normal device slot;
- dashboard device cards can show technical fields when metadata/live IP seams provide them;
- targeted tests cover both the new anti-sharing state and the dashboard device payload.
