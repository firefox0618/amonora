# TASK 100–102 — Frontend quality fixes for both admin UIs

## Status
Complete

## Goal
Remove two noisy classes of frontend-quality issues across both admin surfaces:

- Recharts rendering before containers have a real size
- form fields missing explicit `id` / `name`

## Scope
- `dashboard_v2` chart rendering stability on `overview`, `traffic`, `servers`
- `dashboard_v2` visible form-control normalization
- legacy `dashboard` visible form-control normalization
- legacy spark-chart render guard

## Non-goals
- no backend/API contract changes
- no form submission semantics changes
- no chart dataset changes
- no redesign of either admin UI

## Acceptance criteria
- no normal-navigation Recharts size warning on `overview`, `traffic`, `servers`
- no normal-navigation console warning about visible form fields without `id` or `name`
- both `dashboard` and `dashboard_v2` remain operational

## Validation
- Python dashboard smoke/contract tests
- `dashboard_v2` typecheck
- `dashboard_v2` production build
- manual browser smoke on representative chart and form pages
