# TASK 019 — Dashboard API v2 traffic contract smoke result

## Status
Completed

## What was added
- `tests/test_dashboard_api_v2_traffic_contract.py`

## What is now protected
- `GET /dashboard/api/v2/traffic` returns `401` without session
- `GET /dashboard/api/v2/traffic` returns `200` with valid session
- the top-level response shape expected by `dashboard_v2` is preserved:
  - `overview`
  - `bandwidth_by_server`
  - `connections_by_region`
  - `peak_hours`
  - `top_countries`
  - `traffic_mix`
- `bandwidth_by_server` remains a list-like payload

## Contract focus
- The test set protects the first load-bearing traffic analytics contract used by `dashboard_v2`
- Assertions intentionally stay at the top-level payload boundary and do not freeze nested analytics schema

## Intentionally uncovered
- chart correctness
- force-refresh behavior
- nested analytics series schema
- browser/UI rendering in `dashboard_v2`

## Suggested next step
- only continue to `settings` if config-facing smoke is still worth the maintenance cost
