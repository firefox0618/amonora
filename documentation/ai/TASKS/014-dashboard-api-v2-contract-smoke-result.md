# TASK 014 — Dashboard API v2 contract smoke result

## Status
Completed

## What was added
- `tests/test_dashboard_api_v2_contract.py`

## What is now protected
- `GET /dashboard/api/v2/overview` returns `401` without session
- `GET /dashboard/api/v2/overview` returns `200` with valid session and preserves the top-level shape expected by `dashboard_v2`
- `GET /dashboard/api/v2/payments` returns `401` without session
- `GET /dashboard/api/v2/payments` returns `200` with valid session and preserves the top-level shape expected by `dashboard_v2`

## Contract focus
- The test set protects two load-bearing v2 endpoints:
  - `overview` as the main dashboard backbone payload
  - `payments` as the most sensitive money-facing admin payload after auth/session
- Assertions intentionally target only stable top-level response structure, not every incidental field

## Intentionally uncovered
- broader `/dashboard/api/v2/*` surface such as `users`, `support`, `servers`, `traffic`, `settings`, `knowledge`
- browser/UI rendering in `dashboard_v2`
- full response schema validation
- role/permission matrix for every admin action
- stale-session behavior beyond existing auth/session seam tests

## Suggested next step
- add the next dashboard API contract smoke around a mutable or list-heavy surface:
  - `users`
  - or `support`
