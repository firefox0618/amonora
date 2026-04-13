# TASK 015 — Dashboard API v2 users contract smoke

## Status
Completed

## Goal
Introduce a minimal contract-smoke test set around `GET /dashboard/api/v2/users` so the users surface relied on by `dashboard_v2` is protected against silent API regressions.

## Why
The project already has:
- auth/session seam protection,
- payment finalization protection,
- payment confirmation idempotency protection,
- API contract smoke for `overview` and `payments`.

The next logical API seam is `users`, because it is one of the most central and frequently used dashboard surfaces.
If its contract regresses, a large part of the admin UI becomes misleading or unusable.

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
- `GET /dashboard/api/v2/users`
- `dashboard_v2/src/hooks/use-dashboard.ts`
- `dashboard_v2/src/app/(dashboard)/users/page.tsx`
- `tests/test_dashboard_api_v2_contract.py`

## Current behavior
`users` is an active, load-bearing v2 screen and depends on the `dashboard` backend/API layer.
Its contract is important, but it is not yet protected by focused smoke tests.

## Desired behavior
There should be a small, explicit smoke-level contract test set that verifies:
- unauthorized access is rejected correctly
- authorized access succeeds
- the response keeps the minimal expected top-level shape for v2 consumers
- invalid/stale session behavior is safe

## Scope
- add smoke tests around `GET /dashboard/api/v2/users`
- cover:
  - no session -> `401`
  - valid session -> `200`
  - minimally expected top-level shape:
    - `items`
    - `query`
    - `summary`
- if practical, verify one lightweight invariant about `items` being a list-like payload

## Out of scope
- full users API coverage
- frontend rendering tests
- exhaustive validation of every nested field
- search/filter matrix coverage
- large refactor of users backend/API

## Constraints
- prefer the smallest useful contract
- keep tests deterministic
- avoid brittle snapshot assertions
- validate only load-bearing response structure
- preserve current behavior unless an explicitly scoped bug is found

## Risks
- users payload may include fields that evolve over time
- tests may become too integration-heavy if they depend on rich seed data
- overly deep assertions may create maintenance noise instead of protection

## Acceptance criteria
- `GET /dashboard/api/v2/users` without session is covered for `401`
- `GET /dashboard/api/v2/users` with valid session is covered for `200`
- top-level response shape `items / query / summary` is covered minimally
- intentionally uncovered parts are documented explicitly

## Validation
Manual checks:
- verify the endpoint is genuinely used by `dashboard_v2`
- verify assertions target stable contract fields only
- verify tests are rerunnable and deterministic
- verify no production-only secrets or live dependencies are required

## Deliverables
- users contract smoke tests
- short note on what contract they protect
- explicit list of still-uncovered users API risk areas
- suggested next dashboard API hardening step
