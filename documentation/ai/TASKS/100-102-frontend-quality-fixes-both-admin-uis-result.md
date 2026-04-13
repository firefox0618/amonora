# TASK 100–102 — Frontend quality fixes for both admin UIs — Result

## What changed

### `dashboard_v2`
- added a reusable measured chart wrapper so Recharts pages render only after the container has a real size
- removed percent-height `ResponsiveContainer` usage from `overview`, `traffic`, and `servers`
- completed explicit `id` / `name` coverage for visible controls on:
  - login
  - verify
  - app-shell search / avatar upload
  - overview batch-repair checkboxes
  - users
  - payments
  - support
  - settings
  - knowledge

### legacy `dashboard`
- added explicit `id` values for visible controls in:
  - `login.html`
  - `verify.html`
  - `dashboard.html`
- connected labels to inputs with `for=...` where visible labels existed
- hardened legacy spark-chart rendering so hidden or zero-size nodes are retried on the next frame instead of rendering immediately

## What did not change
- backend routes
- payload shapes
- field names used by backend form handlers
- chart data and business logic

## Notes
- `Input` / `Select` primitives in `dashboard_v2` now fall back to `id=name` when a caller supplies `name` but omits `id`
- legacy hidden inputs were largely left untouched because the target warning concerns visible controls
- this wave is intentionally a UI-quality pass, not a functional refactor
