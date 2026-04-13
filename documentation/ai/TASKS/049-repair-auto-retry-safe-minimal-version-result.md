# TASK 049 — Repair auto-retry (safe minimal version) Result

## Result
Implemented a single safe retry for fresh VPN sync failures.

## What changed
- `bot/payment_flow.py`
  - added `sync_user_vpn_access_with_single_retry(...)`
  - payment finalization now uses the helper and returns:
    - `auto_retry_attempted`
    - `auto_retry_succeeded`
- `dashboard/services.py`
  - manual `Repair VPN` now reuses the same helper
- `tests/test_payment_finalization.py`
  - added coverage for retry success/failure
- `tests/test_dashboard_vpn_repair.py`
  - updated manual repair seam coverage for helper usage

## Trigger points
- post-payment sync verification
- manual dashboard VPN repair action

## Stored events
- `auto_repair_success`
- `auto_repair_failed`

## Explicitly not included
- no background worker
- no retry queue
- no multiple retries
- no retry scheduling
- no automatic device recreation
