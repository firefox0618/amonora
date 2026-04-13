# TASK 019 — Dashboard API v2 traffic contract smoke

## Status
Completed

## Goal
Introduce a minimal contract-smoke test set around `GET /dashboard/api/v2/traffic` so the traffic surface relied on by `dashboard_v2` is protected against silent API regressions.

## Why
The project already has:
- auth/session seam protection,
- payment finalization protection,
- payment confirmation idempotency protection,
- API contract smoke for `overview`, `payments`, `users`, `support`, and `servers`.

The next logical API seam is `traffic`, because it is a neighboring operational surface to `servers` and is relevant to runtime visibility in the new admin UI.
If its contract regresses, the dashboard may remain reachable while losing critical traffic observability.

## Context
Relevant docs:
- `documentation/ARCHITECTURE.md`
- `documentation/FEATURES.md`
- `documentation/REPO_RULES.md`
- `documentation/DASHBOARD_BOUNDARY_MAP.md`
- `documentation/DASHBOARD_COVERAGE_AUDIT.md`
- `documentation/TEST_INVENTORY_AND_RISK_MAP.md`
- `documentation/ai/STATE.md`

Relevant code areas:
- `dashboard/main.py`
- `GET /dashboard/api/v2/traffic`
- `dashboard_v2` hook/page that consumes traffic payload
- existing API smoke harness/tests:
  - `tests/test_dashboard_api_v2_contract.py`
  - `tests/test_dashboard_api_v2_users_contract.py`
  - `tests/test_dashboard_api_v2_support_contract.py`
  - `tests/test_dashboard_api_v2_servers_contract.py`

## Current behavior
`traffic` is part of the active v2 admin surface and depends on the `dashboard` backend/API layer.
Its contract matters for operational visibility, but it is not yet protected by focused smoke tests.

## Desired behavior
There should be a small, explicit smoke-level contract test set that verifies:
- unauthorized access is rejected correctly
- authorized access succeeds
- the response keeps the minimal expected top-level shape for v2 consumers
- invalid/stale session behavior remains safe

## Scope
- add smoke tests around `GET /dashboard/api/v2/traffic`
- cover:
  - no session -> `401`
  - valid session -> `200`
  - minimally expected top-level response shape
- if practical, verify one lightweight invariant about the primary list-like payload

## Out of scope
- full traffic API coverage
- frontend rendering tests
- exhaustive validation of nested analytics fields
- chart correctness
- historical aggregation correctness
- large refactor of traffic backend/API

## Constraints
- prefer the smallest useful contract
- keep tests deterministic
- avoid brittle snapshot assertions
- validate only load-bearing response structure
- preserve current behavior unless an explicitly scoped bug is found

## Risks
- traffic payload may contain evolving chart/series structures
- tests may become too integration-heavy if they depend on live-like data
- overly deep assertions may create maintenance noise instead of protection

## Acceptance criteria
- `GET /dashboard/api/v2/traffic` without session is covered for `401`
- `GET /dashboard/api/v2/traffic` with valid session is covered for `200`
- minimal top-level response shape is covered
- intentionally uncovered parts are documented explicitly

## Validation
Manual checks:
- verify the endpoint is genuinely used by `dashboard_v2`
- verify assertions target stable contract fields only
- verify tests are rerunnable and deterministic
- verify no production-only secrets or live dependencies are required

## Deliverables
- traffic contract smoke tests
- short note on what contract they protect
- explicit list of still-uncovered traffic API risk areas
- suggested next dashboard API hardening step
