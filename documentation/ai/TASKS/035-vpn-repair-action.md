# TASK 035 — VPN repair action (manual re-sync / recreate)

## Status
Completed

## Goal
Allow admin to manually fix users with `vpn_repair_needed` by triggering a safe repair action from `dashboard_v2`, without redesigning the whole VPN system.

## Why
Previous steps already did two important things:

- `033` persisted `vpn_repair_needed`
- `034` surfaced the state in `dashboard_v2`

That made the system honest, but still left a support gap:

- admin could see the problem
- admin still could not trigger a direct repair action

## Scope
- add one backend action:
  - manual VPN re-sync
- reuse existing sync logic
- connect the action from `dashboard_v2` user detail
- clear the repair marker on success
- keep or update the marker on failure

## Out of scope
- bulk repair
- async queue or retry worker
- recreate-device flow
- UI redesign
- payment-flow redesign

## Acceptance criteria
- admin can trigger repair from `dashboard_v2`
- backend reuses existing sync logic
- success clears `vpn_repair_needed`
- failure keeps or updates it
- normal flows remain unchanged

## Validation
- backend service tests:
  - successful sync clears marker
  - failed sync keeps/updates marker
  - no-devices path stays marked as repair-needed
- API smoke:
  - unauthorized call returns `401`
  - authorized call returns sync result shape

