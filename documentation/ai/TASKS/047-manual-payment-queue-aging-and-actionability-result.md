# TASK 047 RESULT — Manual payment queue aging and actionability

## What changed

The overview `System` -> `Payments` block is now more actionable, not just informative.

Added:
- explicit stale definition: `pending manual payment older than 12 hours`
- compact list of oldest pending manual payments
- direct link from each item to `/payments?record_id=...`

## Stored shape

Overview `system_alerts.payments` now includes:
- `stale_definition_hours`
- `oldest_pending_manual_payments`

Each item carries:
- `record_id`
- `user_id`
- `username`
- `telegram_id`
- `created_at`
- `age_hours`
- `is_stale`
- `href`
- `user_href`

## Validation

Updated:
- `tests/test_dashboard_payment_actionability.py`
- `tests/test_dashboard_api_v2_contract.py`
