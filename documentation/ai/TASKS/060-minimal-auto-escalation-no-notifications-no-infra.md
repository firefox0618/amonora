# TASK 060 — Minimal auto-escalation (no notifications, no infra)

## Status
Complete

## Goal
Visually escalate long-lived issues in overview so operators can see not only priority, but also which problems are already going stale.

## Why
After `059`, overview already marked issues with `high / medium / low` priority.

What was still missing:
- time-based urgency
- a lightweight way to show "this has been hanging too long"
- stronger visual emphasis without introducing workers, notifications, or background automation

## Scope
Minimal visual/time-based escalation only:
- no emails
- no cron
- no retry loop
- no alert engine

Escalation is derived from existing timestamps inside overview payload building.

## Implemented thresholds
- repair-needed older than `6h` -> escalated
- pending manual payment older than `12h` -> escalated
- open support ticket older than `24h` -> escalated

## Implemented behavior
- overview payload now carries `is_escalated`
- repair items also carry `marked_age_hours`
- support items also carry `age_hours`
- escalated items get stronger visual treatment in overview
- existing priority can be raised to `high` when escalation applies

## Out of scope
- notifications
- background jobs
- operator assignment
- SLA engine
- infra-level alerting

## Validation
- backend unit tests cover repair/support/payment escalation derivation
- overview contract test updated for new payload fields
- frontend typecheck/build re-confirmed after UI update

## Deliverables
- minimal escalation rules
- overview payload additions
- overview UI urgency treatment
- result note documenting thresholds and limits
