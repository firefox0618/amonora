# TASK 052 — Payment/access repair reason normalization Result

## Result
Introduced a canonical repair reason set and normalized legacy names on read.

## Canonical set
- `post_payment_sync_failed`
- `post_payment_access_incomplete`
- `manual_repair_sync_failed`
- `manual_repair_no_access`
- `manual_repair_no_devices`

## Event-only reasons
- `auto_repair_success`
- `auto_repair_failed`

## Legacy aliases still supported
- `manual_repair_failed`
- `manual_repair_failed_no_access`
- `manual_repair_failed_no_devices`

These are normalized in UI/grouping layers without requiring a DB migration.

## What changed
- new writes now use canonical `manual_repair_*` names
- overview grouping and user detail display normalized reasons
- payment-side repair reasons stayed unchanged because they were already consistent
