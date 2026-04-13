# TASK 039 — Overview attention rail for user-level repair issues Result

## Result
Completed.

## What changed
- Added a minimal overview `attention` payload in `dashboard/v2_data.py`
- Added a compact `Needs attention` rail on overview in `dashboard_v2`
- Included:
  - users with `vpn_repair_needed`
  - repeated failed repair attempts derived from `vpn_repair_events`

## Included signals
- `vpn_repair_needed`
- repeated failed repair attempts for users already in repair-needed state

## Intentionally left for later
- system-level ops alerts
- backup/server alert surfacing
- full alerts center
- scoring/prioritization

## Tests
- `tests/test_dashboard_overview_attention.py`
- `tests/test_dashboard_api_v2_contract.py`
- `tests/test_dashboard_vpn_repair.py`

## Validation
- backend tests passed
- `dashboard_v2` typecheck/build re-confirmed in Windows Node environment
