# TASK 038 — Alerts / attention surface map Result

## Result
Completed.

## What changed
- Added a canonical map of current attention signals:
  - `documentation/ALERTS_ATTENTION_MAP.md`
- Updated navigation/docs state so this map is discoverable

## What the map now covers
- user-level repair/access signals
- overview support/payment/server alerts already present in the system
- documentation-only ops/backup/restore attention gaps
- current visibility gaps between user detail, overview, and ops truth

## Key conclusion
The project already has a real attention layer, but it is fragmented:

- user-level repair signals are visible in user detail
- overview alerts cover services, servers, support, and manual payments
- backup/restore and host-loss risks are still mostly documentation-only truths

## Recommended next tasks
- `039` — overview attention rail for user-level repair issues
- `040` — minimal system ops alerts surface

## Runtime impact
None.

This task was documentation-only and did not change backend, frontend, or production behavior.
