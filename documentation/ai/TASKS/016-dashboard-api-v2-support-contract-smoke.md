# TASK 016 — Dashboard API v2 support contract smoke

## Status
Completed

## Goal
Introduce a minimal contract-smoke test set around `GET /dashboard/api/v2/support` so the support surface relied on by `dashboard_v2` is protected against silent API regressions.

## Why
The project already has:
- auth/session seam protection,
- payment finalization protection,
- payment confirmation idempotency protection,
- API contract smoke for `overview`, `payments`, and `users`.

The next logical API seam is `support`, because it is an active operator-facing dashboard surface with list/detail context and queue metrics.
If its contract regresses, support workflows may appear available while the new UI becomes misleading or partially unusable.

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
- `GET /dashboard/api/v2/support`
- `dashboard_v2/src/hooks/use-dashboard.ts`
- `dashboard_v2/src/app/(dashboard)/support/page.tsx`
- `tests/test_dashboard_api_v2_contract.py`
- `tests/test_dashboard_api_v2_users_contract.py`

## Current behavior
`support` is an active, load-bearing v2 screen and depends on the `dashboard` backend/API layer.
Its contract is important, but it is not yet protected by focused smoke tests.

## Desired behavior
There should be a small, explicit smoke-level contract test set that verifies:
- unauthorized access is rejected correctly
- authorized access succeeds
- the response keeps the minimal expected top-level shape for v2 consumers
- invalid/stale session behavior is safe

## Scope
- add smoke tests around `GET /dashboard/api/v2/support`
- cover:
  - no session -> `401`
  - valid session -> `200`
  - minimally expected top-level shape:
    - `tickets`
    - `counts`
    - `filter_mode`
    - `query`
    - `admin_choices`
- if practical, verify one lightweight invariant about `tickets` being a list-like payload

## Out of scope
- full support API coverage
- detail-route coverage for `/dashboard/api/v2/support/{ticket_user_id}`
- reply/assign/transfer/close mutation coverage
- frontend rendering tests
- exhaustive validation of every nested field
- large refactor of support backend/API

## Constraints
- prefer the smallest useful contract
- keep tests deterministic
- avoid brittle snapshot assertions
- validate only load-bearing response structure
- preserve current behavior unless an explicitly scoped bug is found

## Risks
- support payload is more stateful than simple list endpoints
- tests may become too integration-heavy if they depend on real ticket history setup
- overly deep assertions may create maintenance noise instead of protection

## Acceptance criteria
- `GET /dashboard/api/v2/support` without session is covered for `401`
- `GET /dashboard/api/v2/support` with valid session is covered for `200`
- top-level response shape `tickets / counts / filter_mode / query / admin_choices` is covered minimally
- intentionally uncovered parts are documented explicitly

## Validation
Manual checks:
- verify the endpoint is genuinely used by `dashboard_v2`
- verify assertions target stable contract fields only
- verify tests are rerunnable and deterministic
- verify no production-only secrets or live dependencies are required

## Deliverables
- support contract smoke tests
- short note on what contract they protect
- explicit list of still-uncovered support API risk areas
- suggested next dashboard API hardening step
