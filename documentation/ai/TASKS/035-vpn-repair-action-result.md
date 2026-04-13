# TASK 035 — VPN repair action (manual re-sync / recreate) Result

## Result
Completed.

## What changed
- Added backend service orchestration for manual VPN repair:
  - `repair_user_vpn_access(...)` in `dashboard/services.py`
- Added API endpoint:
  - `POST /dashboard/api/v2/users/{user_id}/repair-vpn`
- Added `dashboard_v2` user-detail action:
  - `Repair VPN`

## Behavior
- If manual re-sync succeeds:
  - `vpn_repair_needed` is cleared
  - the warning block disappears after refresh
- If manual re-sync fails:
  - repair-needed state stays active
  - reason is updated to `manual_repair_failed`
- If repair cannot even start safely:
  - state stays active with a narrower reason:
    - `manual_repair_failed_no_access`
    - `manual_repair_failed_no_devices`

## Tests
- `tests/test_dashboard_vpn_repair.py`

Covered:
- service success -> marker cleared
- service failure -> marker kept
- service no-devices guard -> marker kept
- API unauthorized -> `401`
- API authorized -> sync result returned

## Still not covered
- no bulk repair
- no retry queue
- no recreate-device repair flow
- no dedicated repair history UI

