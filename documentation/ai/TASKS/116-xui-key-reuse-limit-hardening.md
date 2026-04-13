# TASK 116 — x-ui key reuse limit hardening

## Status
Completed

## Goal
Reduce the gap where one issued VPN key could be reused as a de-facto unlimited multi-device credential even though the product limits users by device count.

## Scope
- `bot/vpn_api.py`
- `bot/handlers/devices.py`
- focused tests for `3x-ui` payload behavior
- documentation/state updates for the new behavior

## What changed
- new `x-ui` VLESS and Trojan clients now use `limitIp = 1` at creation time;
- VLESS/Trojan sync paths now preserve that limit instead of resetting to unlimited;
- bot key/QR reissue paths now best-effort re-apply the limit for existing `x-ui` devices before sending credentials again;
- Denmark `xray_core` was intentionally left unchanged because the current provider seam does not expose an equivalent panel-side IP-limit control.

## Constraints
- keep the change narrow and reversible;
- do not refactor provisioning boundaries across `bot`, `dashboard`, and `backend`;
- do not claim hardware-bound `1 key = 1 physical device` enforcement where the runtime only provides an IP-based limit.

## Acceptance criteria
- newly created `x-ui`-backed keys are no longer provisioned with unlimited `limitIp`;
- expiry/sync operations do not silently revert the limit back to `0`;
- targeted tests protect the payload behavior;
- docs and AI state mention the new behavior and the Denmark gap explicitly.
