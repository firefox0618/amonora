# TASK 020 — Dashboard API v2 settings contract smoke

## Status
Completed

## Goal
Introduce a minimal contract-smoke test set around `GET /dashboard/api/v2/settings` so the settings surface relied on by `dashboard_v2` is protected against silent API regressions.

## Why
The project already has:
- auth/session seam protection,
- payment finalization protection,
- payment confirmation idempotency protection,
- API contract smoke for `overview`, `payments`, `users`, `support`, `servers`, and `traffic`.

`settings` is the last obvious v2 operational/config surface worth protecting at smoke level without entering mutation-heavy behavior.
If its read contract regresses, the dashboard may remain reachable while losing core configuration visibility.

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
- `GET /dashboard/api/v2/settings`
- `dashboard_v2` hook/page that consumes settings payload
- existing API smoke harness/tests

## Current behavior
`settings` is part of the active v2 admin surface and depends on the `dashboard` backend/API layer.
Its contract matters for configuration visibility, but it is not yet protected by focused smoke tests.

## Desired behavior
There should be a small, explicit smoke-level contract test set that verifies:
- unauthorized access is rejected correctly
- authorized access succeeds
- the response keeps the minimal expected top-level shape for v2 consumers
- invalid/stale session behavior remains safe

## Scope
- add smoke tests around `GET /dashboard/api/v2/settings`
- cover:
  - no session -> `401`
  - valid session -> `200`
  - minimally expected top-level response shape
- if practical, verify one lightweight invariant about the primary list-like payload

## Out of scope
- settings mutations
- env updates
- service actions
- tariff changes
- frontend rendering tests
- exhaustive validation of nested config fields

## Constraints
- prefer the smallest useful contract
- keep tests deterministic
- avoid brittle snapshot assertions
- validate only load-bearing response structure
- preserve current behavior unless an explicitly scoped bug is found

## Risks
- settings payload is broad and partially operational
- tests may become too integration-heavy if they depend on live config
- overly deep assertions may create maintenance noise

## Acceptance criteria
- `GET /dashboard/api/v2/settings` without session is covered for `401`
- `GET /dashboard/api/v2/settings` with valid session is covered for `200`
- minimal top-level response shape is covered
- intentionally uncovered parts are documented explicitly

## Validation
Manual checks:
- verify the endpoint is genuinely used by `dashboard_v2`
- verify assertions target stable contract fields only
- verify tests are rerunnable and deterministic
- verify no production-only secrets or live dependencies are required

## Deliverables
- settings contract smoke tests
- short note on what contract they protect
- explicit list of still-uncovered settings API risk areas
- suggested next dashboard API hardening step
