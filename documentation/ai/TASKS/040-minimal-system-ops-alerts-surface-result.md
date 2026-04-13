# TASK 040 — Minimal system ops alerts surface Result

## Result
Completed.

## What changed
- Added a minimal overview `system_alerts` payload
- Added a compact `System status` block on `dashboard_v2` overview
- Included:
  - backup freshness
  - support backlog
  - manual payment confirmation queue

## Signal sources
- backup freshness:
  - local backup artifact heuristic from `dashboard/services.py`
- support backlog:
  - existing support counts
- manual payment queue:
  - existing payment review counts

## Intentionally left for later
- server/node monitoring expansion
- backup/provider snapshot alerts from docs-only truth
- external monitoring integrations
- full alerts center

## Tests
- `tests/test_dashboard_system_alerts.py`
- `tests/test_dashboard_api_v2_contract.py`

## Validation
- backend tests passed
- `dashboard_v2` typecheck/build re-confirmed in Windows Node environment
