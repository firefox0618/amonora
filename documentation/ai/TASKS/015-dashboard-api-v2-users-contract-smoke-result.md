# TASK 015 — Dashboard API v2 users contract smoke result

## Status
Completed

## What was added
- `tests/test_dashboard_api_v2_users_contract.py`

## What is now protected
- `GET /dashboard/api/v2/users` returns `401` without session
- `GET /dashboard/api/v2/users` returns `200` with valid session
- the top-level response shape expected by `dashboard_v2` is preserved:
  - `items`
  - `query`
  - `summary`
- `items` remains a list-like payload

## Contract focus
- The test set protects the first load-bearing users list contract used by `dashboard_v2`
- Assertions intentionally stay at the top-level payload boundary and do not try to freeze the full nested `UserRow` schema

## Intentionally uncovered
- search/filter behavior
- nested field schema for `UserRow`
- `/dashboard/api/v2/users/{user_id}` detail contract
- mutations under `/users/{user_id}/...`
- browser/UI rendering in `dashboard_v2`

## Suggested next step
- add the next dashboard API contract smoke for `support`
