# TASK 037 — VPN repair event log Result

## Result
Completed.

## What changed
- Added a minimal persistent model:
  - `VpnRepairEvent` in `backend/core/models.py`
- Added DB helpers:
  - `create_vpn_repair_event(...)`
  - `list_vpn_repair_events(...)`
- Extended manual repair orchestration:
  - `repair_user_vpn_access(...)` now writes an event on every repair outcome
- Extended existing user detail payload:
  - recent repair events are included in backend/v2 user detail
- Added a small `dashboard_v2` user-detail section:
  - `Последние попытки repair`

## Stored fields
- `user_id`
- `result`
- `reason`
- `created_at`

## Behavior
- successful manual repair writes:
  - `result = success`
  - `reason = manual_repair`
- failed manual repair writes:
  - `result = failed`
  - `reason = manual_repair_failed`
- guarded repair failures also write narrower reasons:
  - `manual_repair_failed_no_access`
  - `manual_repair_failed_no_devices`

## Tests
- `tests/test_dashboard_vpn_repair.py`
- `tests/test_payment_finalization.py`

Covered:
- success -> success event written
- sync failure -> failed event written
- no-devices guard -> failed event written
- recent events included in user detail
- `dashboard_v2` typecheck/build re-confirmed in Windows Node environment via a dedicated PowerShell runner

## Still not covered
- no retry queue
- no aggregate analytics
- no bulk repair history
- no recreate-device repair workflow
