# TASK 010 — Dashboard auth/session smoke tests

## Status
Completed

## Goal
Add the first focused smoke-level test protection for the dashboard auth and admin session flow.

## Why
The current test/risk map identified dashboard auth/session as one of the highest-risk, lowest-protection areas in the project.

This flow is critical because:
- it is the entry point into the admin contour;
- it mixes `dashboard`, Telegram verification, session persistence, and runtime config;
- a break here can make the admin surface unusable even if backend and `dashboard_v2` are otherwise alive.

## Context
Relevant docs:
- `documentation/TEST_INVENTORY_AND_RISK_MAP.md`
- `documentation/ARCHITECTURE.md`
- `documentation/REPO_RULES.md`
- `documentation/RUNBOOK.md`
- `documentation/product/DASHBOARD_BOUNDARY_MAP.md`
- `documentation/product/DASHBOARD_COVERAGE_AUDIT.md`
- `documentation/ai/STATE.md`

Relevant code areas:
- `dashboard/security.py`
- `dashboard/models.py`
- `dashboard/services.py`
- `dashboard/templates/login.html`
- `dashboard/templates/verify.html`
- `dashboard_v2/src/app/login/page.tsx`
- `dashboard_v2/src/app/verify/page.tsx`
- `dashboard_v2/src/app/auth/request-code/route.ts`
- `dashboard_v2/src/app/auth/verify/route.ts`

## Current behavior
The dashboard auth/session flow is operationally important, but no explicit smoke-level test protection is currently mapped for:
- login credential validation
- verify-code transition
- session creation
- session expiry / invalid session behavior
- basic protected-route expectations

## Desired behavior
The project should have a small but real smoke test layer that protects the most important dashboard auth/session paths against obvious regression.

## Scope
- inspect the current dashboard auth/session implementation
- identify the smallest stable test seam
- add smoke-level tests for the most important auth/session behavior
- keep the first pass narrow and practical

Target behaviors to protect if feasible in the first pass:
- valid login path starts verification flow
- invalid login path fails safely
- verify flow handles valid vs invalid code/state correctly
- session token/session record creation path is covered
- expired or missing session is rejected on protected access

## Out of scope
- redesigning auth
- replacing Telegram verification
- removing legacy login/verify pages
- broad auth refactor
- frontend UI snapshot testing
- full end-to-end browser automation

## Constraints
- prefer narrow smoke protection over ambitious auth test architecture
- do not assume `dashboard` auth is legacy; it remains an active backend responsibility
- do not break current login/verify behavior while adding tests
- avoid introducing tests that require live Telegram or production services

## Risks
- auth flow may be tightly coupled to runtime config and admin seed data
- session creation may depend on DB state or current schema assumptions
- `dashboard_v2` frontend routes may obscure where the real backend seam lives
- a too-broad first pass could create flaky or high-maintenance tests

## Acceptance criteria
- dashboard auth/session smoke test file(s) exist
- the first-pass tests cover at least the most critical auth/session seam
- if full login->verify->session coverage is too coupled for the first pass, protect the narrowest stable backend auth/session seam and document the skipped parts explicitly
- tests do not require live Telegram delivery
- the new coverage meaningfully reduces regression risk for admin login/session behavior
- any important uncovered auth gaps are explicitly documented

## Validation
Manual checks:
- verify the tests target the real active auth/session backend path
- verify the tests are narrow enough to run locally without production dependencies
- verify no legacy-cleanup assumptions are introduced accidentally

## Deliverables
- dashboard auth/session smoke tests
- short implementation summary
- explicit note on what auth/session behavior is still not covered
