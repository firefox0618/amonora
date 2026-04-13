# TASK 047 — Manual payment queue aging and actionability

## Status
Completed

## Goal
Make the manual payment queue more actionable by surfacing aging/stale items clearly and giving admins a faster path from overview to the exact payment/user context that needs action.

## Outcome

Overview payments status now includes:
- explicit stale rule: older than `12h`
- `oldest_pending_manual_payments`
- direct links into the relevant payment record

## Scope kept intentionally narrow

Included:
- stale definition
- top oldest pending manual payments slice
- overview navigation into payment context

Not included:
- queue redesign
- assignments
- notifications
- support-bot changes
