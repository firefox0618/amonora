# TASK 038 — Alerts / attention surface map

## Status
Completed

## Goal
Collect the current attention signals across product and operations layers and define where they should eventually be surfaced in `dashboard_v2`.

## Why
The system already contains real attention-worthy states:

- VPN repair-needed state
- repair history
- support queue pressure
- manual payment queue
- service/server degradation
- backup and restore posture gaps

But these signals are currently split across:

- user detail
- overview alerts
- support/payments/servers sections
- operator knowledge
- documentation-only ops notes

## Scope
- map existing signals only
- separate user-level and system-level attention states
- record current visibility and gaps
- suggest minimal future UI placement

## Out of scope
- no runtime changes
- no new alert generation logic
- no dashboard UI implementation
- no notification channels

## Acceptance criteria
- one canonical map of current attention states exists
- each signal has source, visibility, severity, and suggested UI placement
- user-level and system-level signals are separated
- next 1–2 small implementation candidates are proposed

## Validation
- verify VPN/access signals against current repair flow and user detail
- verify overview alerts against existing dashboard service logic
- verify ops/backup/restore gaps against existing documentation, not assumptions

