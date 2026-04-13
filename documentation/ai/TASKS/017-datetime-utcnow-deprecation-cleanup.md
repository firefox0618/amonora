# TASK 017 — datetime.utcnow() deprecation cleanup

## Status
Completed

## Goal
Replace deprecated `datetime.utcnow()` usage in `dashboard/security.py` with a timezone-aware equivalent, without changing the current auth/session behavior.

## Why
Current smoke and contract tests are green, but test runs still surfaced a `DeprecationWarning` from `dashboard/security.py`.
This is a small, safe cleanup target that improves future compatibility without widening scope.

## Context
Relevant docs:
- `documentation/REPO_RULES.md`
- `documentation/TEST_INVENTORY_AND_RISK_MAP.md`
- `documentation/ai/STATE.md`

Relevant code areas:
- `dashboard/security.py`
- auth/session-related helpers touched by:
  - `tests/test_dashboard_auth_session.py`
  - `tests/test_dashboard_api_v2_contract.py`
  - `tests/test_dashboard_api_v2_users_contract.py`
  - `tests/test_dashboard_api_v2_support_contract.py`

## Current behavior
The auth/security code used `datetime.utcnow()`, which raised a deprecation warning during tests.

## Desired behavior
`dashboard/security.py` should use a timezone-aware datetime source with no functional regression in auth/session behavior and no deprecation warning from this code path.

## Scope
- identify the exact `datetime.utcnow()` usage in `dashboard/security.py`
- replace it with the smallest correct timezone-aware equivalent
- keep the surrounding auth/session semantics unchanged
- rerun the relevant auth/API smoke tests

## Out of scope
- auth redesign
- session model changes
- broad datetime cleanup across the whole repo
- refactoring unrelated warning sources
- changing production behavior unless a bug is discovered

## Constraints
- keep the patch minimal
- preserve current behavior
- avoid broad search-and-replace across unrelated modules
- prefer the clearest standard-library timezone-aware approach

## Risks
- naive/aware datetime mixing could surface if surrounding code assumes naive UTC
- an over-broad cleanup could touch unrelated flows
- test silence must not come at the cost of behavior drift

## Acceptance criteria
- deprecated `datetime.utcnow()` usage in `dashboard/security.py` is removed
- relevant auth/API smoke tests still pass
- the warning no longer comes from this code path
- no unrelated auth/session behavior changes are introduced

## Validation
Manual checks:
- verify the replacement is timezone-aware
- verify tests touching auth/session and dashboard API still pass
- verify the patch is narrowly scoped to `dashboard/security.py`

## Deliverables
- minimal cleanup patch in `dashboard/security.py`
- short note on what changed
- confirmation of rerun test results
