# TASK 138 — Denmark single-IP enforcement

## Status
Completed

## Goal
Add a real single-key anti-sharing path for Denmark `xray_core`, where `3x-ui`-style `limitIp = 1` does not exist.

## Scope
- `ops/xray_single_ip_enforcer.py`
- `ops/systemd/amonora-dk-single-ip-enforcer.service`
- `ops/systemd/amonora-dk-single-ip-enforcer.timer`
- focused unit tests

## What changed
- Denmark now has a dedicated enforcement worker for `xray_core`;
- the worker reads `Xray access.log`, keeps a short active-IP lease per managed client email, and rewrites `routing.rules` so that a given key is allowed only from its leased public IP and blocked from other IPs;
- `device_`, `dashboard_`, and `landing_bridge_` emails are covered; `test_*` and `dk-main` are excluded;
- access/error log paths are enforced into the live Denmark Xray config by the same worker.

## Constraints
- no fake hardware-binding claims;
- no return of Denmark to `3x-ui`;
- no destructive rewrites of the Denmark client list.

## Acceptance criteria
- future Denmark keys enter the same single-key anti-sharing model after first live access;
- existing Denmark keys become enforceable after the worker is deployed and access logging is enabled;
- test/admin profiles remain excluded from the enforcement set;
- tests protect lease updates and generated routing rules.
