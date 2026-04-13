# TASK 016 — Dashboard API v2 support contract smoke result

## Status
Completed

## What was added
- `tests/test_dashboard_api_v2_support_contract.py`

## What is now protected
- `GET /dashboard/api/v2/support` returns `401` without session
- `GET /dashboard/api/v2/support` returns `200` with valid session
- the top-level response shape expected by `dashboard_v2` is preserved:
  - `tickets`
  - `counts`
  - `filter_mode`
  - `query`
  - `selected_ticket`
  - `admin_choices`
- `tickets` remains a list-like payload

## Contract focus
- The test set protects the first load-bearing support queue contract used by `dashboard_v2`
- Assertions intentionally stay at the top-level payload boundary and do not try to freeze nested ticket/history shape

## Intentionally uncovered
- `/dashboard/api/v2/support/{ticket_user_id}` detail contract
- assign/transfer/reply/close mutations
- filter/search matrix behavior
- nested ticket schema and selected-ticket content
- browser/UI rendering in `dashboard_v2`

## Suggested next step
- fix the `datetime.utcnow()` deprecation warning in `dashboard/security.py`
