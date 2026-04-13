# TASK 060 — Minimal auto-escalation (no notifications, no infra) Result

## Result
Overview now escalates stale issues visually instead of treating all problems with the same static urgency.

## Escalated issue types
- repair-needed users older than `6h`
- pending manual payments older than `12h`
- open support tickets older than `24h`

## What changed
- overview payload now carries `is_escalated` for repair, payment, and support attention items
- repair items now expose `marked_age_hours`
- support tickets now expose `age_hours`
- overview UI shows stronger urgency markers for escalated items

## What stayed intentionally simple
- no notifications
- no background infrastructure
- no automatic actions
- no escalation outside overview visibility
