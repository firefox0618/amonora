# TASK 018 — Dashboard API v2 servers contract smoke result

## Status
Completed

## What was added
- `tests/test_dashboard_api_v2_servers_contract.py`

## What is now protected
- `GET /dashboard/api/v2/servers` returns `401` without session
- `GET /dashboard/api/v2/servers` returns `200` with valid session
- the top-level response shape expected by `dashboard_v2` is preserved:
  - `summary`
  - `nodes`
  - `selected_node`
  - `vpn_summary`
  - `managed_servers`
- `nodes` remains a list-like payload

## Contract focus
- The test set protects the first load-bearing servers list contract used by `dashboard_v2`
- Assertions intentionally stay at the top-level payload boundary and do not freeze nested node metrics or detail structure

## Intentionally uncovered
- `GET /dashboard/api/v2/servers/{server_id}`
- force-refresh behavior
- server creation and status mutations
- nested node schema
- browser/UI rendering in `dashboard_v2`

## Suggested next step
- only continue to another seam if there is a clear payoff; otherwise pause API hardening here
