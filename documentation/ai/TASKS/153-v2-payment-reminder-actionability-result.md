# TASK 153 — V2 payment reminder actionability result

## Status
Completed

## What changed
- `dashboard/v2_data.py` now includes `can_send_reminder` in the serialized payment payload for `dashboard/ui`;
- the `v2` payment detail now stays aligned with the backend reminder actionability rules from `dashboard/services.py`;
- regression coverage now checks that open `sbp_manual` payments expose the reminder flag in both serializers.

## Validation
- `./venv/bin/python -m unittest tests.test_dashboard_payment_actionability`
- production verification on `record_id=141` after backend restart
