# TASK 065 — Repair reason normalization result

## Status
Done

## What changed
- canonical repair reason constants remain the source of truth in `bot/repair_reasons.py`
- legacy manual-repair aliases are normalized before reaching dashboard payloads
- dashboard payloads now carry both:
  - canonical reason code
  - human-readable label

## Canonical repair reasons
- `post_payment_sync_failed`
- `post_payment_access_incomplete`
- `manual_repair_sync_failed`
- `manual_repair_no_access`
- `manual_repair_no_devices`

## Event-only reasons
- `auto_repair_success`
- `auto_repair_failed`

## Legacy aliases still supported
- `manual_repair_failed` -> `manual_repair_sync_failed`
- `manual_repair_failed_no_access` -> `manual_repair_no_access`
- `manual_repair_failed_no_devices` -> `manual_repair_no_devices`

## UI effect
- overview now shows readable repair reasons
- user detail repair state/history now show readable labels
- payments linked user context now shows readable repair labels

## What did not change
- repair behavior
- repair source/outcome model
- repair prioritization/escalation logic

## Follow-up
- `066` should normalize `repair_source` and `repair_outcome`
- `067` should simplify overview and remove remaining operator noise
