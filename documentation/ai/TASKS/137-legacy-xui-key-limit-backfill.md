# TASK 137 — legacy x-ui key-limit backfill

## Status
Completed

## Goal
Close the remaining gap where old `x-ui` VPN keys, issued before the single-IP hardening pass, could still behave like effectively unlimited reusable credentials even though new keys already use `limitIp = 1`.

## Scope
- `bot/device_limit_hardening.py`
- `ops/local/backfill_xui_single_ip_limits_2026_03_26.py`
- focused tests for x-ui vs xray-core handling
- state/runbook updates for the rollout requirement

## What changed
- added a shared helper that reuses the existing `x-ui` sync paths to re-apply single-IP limits on legacy `VLESS` and `Trojan` devices;
- added a one-shot rollout script for running that backfill safely from the core host;
- explicit skip behavior was added for Denmark `xray_core`, because current provider seam still has no equivalent limit control;
- test coverage now protects the new backfill helper.

## Constraints
- keep the change narrow and reversible;
- do not invent a fake “hardware-bound” device identity mechanism;
- do not claim Denmark `xray_core` is fixed by the same rollout when the provider seam still lacks an equivalent primitive.

## Acceptance criteria
- old `x-ui` keys can be re-synced through the normal access sync paths without rewriting provisioning;
- rollout can be targeted to one user or a limited slice before a full pass;
- tests protect the x-ui path and the explicit xray-core skip;
- docs mention that repo deploy alone does not retrofit old keys.
