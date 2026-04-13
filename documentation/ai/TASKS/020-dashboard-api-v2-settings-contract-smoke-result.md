# TASK 020 — Dashboard API v2 settings contract smoke result

## Status
Completed

## What was added
- `tests/test_dashboard_api_v2_settings_contract.py`

## What is now protected
- `GET /dashboard/api/v2/settings` returns `401` without session
- `GET /dashboard/api/v2/settings` returns `200` with valid session
- the top-level response shape expected by `dashboard_v2` is preserved:
  - `service_statuses`
  - `logs`
  - `env_rows`
  - `api_keys`
  - `audits`
  - `tariffs`
  - `tariff_options`
  - `docs`
  - `docs_settings`
  - `managed_servers`
  - `payment_methods`
- `env_rows` remains a list-like payload

## Contract focus
- The test set protects the read-only settings/config visibility contract used by `dashboard_v2`
- Assertions intentionally stay at the top-level payload boundary and do not freeze nested config structures or mutation behavior

## Intentionally uncovered
- settings mutations
- service actions
- env/tariff update behavior
- nested config schema
- browser/UI rendering in `dashboard_v2`

## Suggested next step
- pause API hardening here and capture an end-of-stage checkpoint
