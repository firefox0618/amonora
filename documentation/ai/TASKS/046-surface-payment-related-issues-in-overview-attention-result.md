# TASK 046 RESULT — Surface payment-related issues in overview attention

## What changed

Overview now surfaces payment-related attention in two places:

### User-level
- repair-needed users now carry `is_payment_related`
- overview summary now includes `payment_related_repairs`
- payment-origin repair cases stay visible inside the existing attention rail

### System-level
- payments system block now also shows `stale_pending_confirmations`

## Signals included

Payment-related repair reasons currently include:
- `post_payment_access_incomplete`
- `post_payment_sync_failed`

## Validation

Updated:
- `tests/test_dashboard_overview_attention.py`
- `tests/test_dashboard_api_v2_contract.py`

Confirmed after this task wave:
- `dashboard_v2` typecheck
- `dashboard_v2` build
