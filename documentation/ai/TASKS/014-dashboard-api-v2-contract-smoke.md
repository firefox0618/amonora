# TASK 014 — Dashboard API v2 contract smoke

## Status
Completed

## Goal
Introduce a minimal contract-smoke test set around the most critical `dashboard/api/v2/*` endpoints so the backend/API surface relied on by `dashboard_v2` is protected against silent contract regressions.

## Why
The project now has:
- auth/session seam protection,
- payment finalization seam protection,
- external payment idempotency guard protection.

The next high-risk seam is the API contract between `dashboard` and `dashboard_v2`.
If this contract regresses, the new UI may remain “up” while breaking in subtle or partial ways.

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
- `/dashboard/api/v2/*` routes
- auth/session dependency used by protected API routes
- any existing smoke/integration tests touching dashboard API
- `tests/test_dashboard_auth_session.py`

## Current behavior
`dashboard_v2` depends on the `dashboard` backend/API layer.
The exact API surface is active and critical, but currently only parts of auth/session protection are covered.
Broader v2 API contract stability is not yet protected by focused smoke tests.

## Desired behavior
There should be a small, explicit smoke-level contract test set that verifies:
- unauthorized access behaves as expected
- at least one protected route works with a valid session
- response shape for selected critical endpoints remains stable enough for v2 expectations
- invalid/missing session behavior is safe and consistent

## Scope
- identify the smallest useful set of critical `/dashboard/api/v2/*` endpoints
- add smoke tests around:
  - unauthorized request to protected API endpoint -> expected 401 behavior
  - valid session request to selected protected endpoint -> expected 200 behavior
  - selected endpoint returns minimally expected response shape/keys
  - invalid or stale session is rejected safely
- document what remains intentionally uncovered

## Out of scope
- full endpoint coverage of all `dashboard/api/v2/*`
- frontend `dashboard_v2` browser/E2E testing
- auth redesign
- large API refactor
- UI rendering assertions
- exhaustive schema validation for every response

## Constraints
- prefer the smallest useful contract set
- keep tests deterministic
- avoid brittle snapshot-style assertions
- validate only load-bearing response structure, not every incidental field
- preserve current behavior unless an explicitly scoped bug is found

## Risks
- endpoint behavior may depend on data setup that is awkward to isolate
- tests may accidentally become too integration-heavy
- response shapes may include unstable/nonessential fields
- session assumptions may differ between legacy and v2 consumers

## Acceptance criteria
- at least one protected `dashboard/api/v2/*` endpoint is covered for 401 behavior
- at least one protected `dashboard/api/v2/*` endpoint is covered for successful authorized behavior
- selected response shape/required keys are covered at least minimally
- invalid/stale session rejection is covered where practical
- intentionally uncovered API surface is documented explicitly

## Validation
Manual checks:
- verify tested endpoints are genuinely used or load-bearing for `dashboard_v2`
- verify assertions focus on stable contract fields
- verify tests are rerunnable and deterministic
- verify no production-only secrets or live dependencies are required

## Deliverables
- dashboard API v2 contract smoke tests
- short note on what contract they protect
- explicit list of still-uncovered API risk areas
- suggested next dashboard API hardening step
