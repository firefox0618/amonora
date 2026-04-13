# TASK 039 — Overview attention rail for user-level repair issues

## Status
Completed

## Goal
Add a minimal `Needs attention` rail to overview so admins can immediately see the most important user-level repair issues without opening user detail first.

## Why
The project already had:

- persistent `vpn_repair_needed`
- manual `Repair VPN` action
- repair attempt history
- a mapped attention model in `ALERTS_ATTENTION_MAP.md`

But these signals were still mostly discovered inside user detail.

## Scope
- extend the overview payload with a compact user-level attention block
- first pass covers:
  - users with `vpn_repair_needed`
  - repeated failed repair attempts for those users
- add a small overview rail in `dashboard_v2`

## Out of scope
- system-level ops alerts
- full alerts center
- notifications
- retry automation
- broad overview redesign

## Acceptance criteria
- overview shows a visible `Needs attention` section
- `vpn_repair_needed` users are surfaced
- repeated failed repairs are shown when already derivable from existing history
- items link naturally to user detail
- normal overview behavior remains intact

## Validation
- backend helper test for repair-attention payload
- overview API contract updated for the new top-level `attention` block
- targeted backend test run
- frontend typecheck/build re-check in Windows Node environment

