# TASK 018 — Dashboard API v2 servers contract smoke

## Status
Completed

## Goal
Introduce a minimal contract-smoke test set around `GET /dashboard/api/v2/servers` so the servers surface relied on by `dashboard_v2` is protected against silent API regressions.

## Why
The project already has protection for:
- auth/session
- payment finalization
- payment confirmation idempotency
- `overview`
- `payments`
- `users`
- `support`

The next strongest load-bearing seam is `servers`.
It is more central than `traffic`, more operationally important than `knowledge`, and less configuration-heavy than `settings`.
If its contract regresses, the new admin UI loses one of its core runtime-control surfaces and adjacent monitoring views become misleading.

## Context
Relevant docs:
- `documentation/ARCHITECTURE.md`
- `documentation/RUNBOOK.md`
- `documentation/DASHBOARD_BOUNDARY_MAP.md`
- `documentation/DASHBOARD_COVERAGE_AUDIT.md`
- `documentation/TEST_INVENTORY_AND_RISK_MAP.md`
- `documentation/ai/STATE.md`

Relevant code areas:
- `dashboard/main.py`
- `GET /dashboard/api/v2/servers`
- `dashboard_v2/src/hooks/use-dashboard.ts`
- `dashboard_v2/src/app/(dashboard)/servers/page.tsx`
- `tests/test_dashboard_api_v2_contract.py`
- `tests/test_dashboard_api_v2_users_contract.py`
- `tests/test_dashboard_api_v2_support_contract.py`

## Current behavior
`servers` is an active, load-bearing v2 screen and depends on the `dashboard` backend/API layer.
Its payload drives both list and detail context for managed nodes and is used as a live operational surface.

## Desired behavior
There should be a small, explicit smoke-level contract test set that verifies:
- unauthorized access is rejected correctly
- authorized access succeeds
- the response keeps the minimal expected top-level shape for v2 consumers
- invalid/stale session behavior is safe

## Scope
- add smoke tests around `GET /dashboard/api/v2/servers`
- cover:
  - no session -> `401`
  - valid session -> `200`
  - minimally expected top-level shape:
    - `summary`
    - `nodes`
    - `selected_node`
    - `vpn_summary`
    - `managed_servers`
- if practical, verify one lightweight invariant about `nodes` being a list-like payload

## Out of scope
- full servers API coverage
- `POST /dashboard/api/v2/servers`
- `POST /dashboard/api/v2/servers/{server_id}/status`
- browser/UI rendering tests
- exhaustive validation of every nested node field
- force-refresh behavior

## Constraints
- prefer the smallest useful contract
- keep tests deterministic
- avoid brittle snapshot assertions
- validate only load-bearing response structure
- preserve current behavior unless an explicitly scoped bug is found

## Risks
- `servers` payload is richer than simple list endpoints
- tests may become too integration-heavy if they depend on live metrics setup
- overly deep assertions may create maintenance noise

## Acceptance criteria
- `GET /dashboard/api/v2/servers` without session is covered for `401`
- `GET /dashboard/api/v2/servers` with valid session is covered for `200`
- top-level response shape `summary / nodes / selected_node / vpn_summary / managed_servers` is covered minimally
- intentionally uncovered parts are documented explicitly

## Validation
Manual checks:
- verify the endpoint is genuinely used by `dashboard_v2`
- verify assertions target stable contract fields only
- verify tests are rerunnable and deterministic
- verify no production-only secrets or live dependencies are required

## Deliverables
- servers contract smoke tests
- short note on what contract they protect
- explicit list of still-uncovered servers API risk areas
- suggested next dashboard API hardening step
