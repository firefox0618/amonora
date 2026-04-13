# TASK 013 — confirm_external_payment_record idempotency tests

## Status
Completed

## Goal
Introduce focused tests for `confirm_external_payment_record` so the payment-confirmation idempotency boundary is explicitly protected against duplicate processing regressions.

## Why
`finalize_subscription_payment` is now protected as an orchestration seam, and tests have confirmed that it is not idempotent by itself.
That makes the payment-record confirmation layer even more important: it is the current guard that prevents the same external payment from being finalized twice.

## Context
Relevant docs:
- `documentation/DOMAIN.md`
- `documentation/FEATURES.md`
- `documentation/REPO_RULES.md`
- `documentation/TEST_INVENTORY_AND_RISK_MAP.md`
- `documentation/ai/STATE.md`

Relevant code areas:
- `bot/db.py`
- `confirm_external_payment_record`
- external payment record model / status fields
- any existing crypto/manual payment tests near this flow
- `tests/test_payment_finalization.py`

## Current behavior
Payment finalization orchestration is now covered by tests, but the idempotency guard that prevents duplicate confirmation is still only implicitly trusted.
If this guard regresses, the same payment event may re-enter finalization and incorrectly extend entitlement more than once.

## Desired behavior
There should be a small, explicit test set that proves:
- first confirmation marks the record as confirmed
- first confirmation returns `just_confirmed = True`
- repeated confirmation does not re-confirm the record
- repeated confirmation returns `just_confirmed = False`
- already confirmed records remain stable
- invalid lookup/input is handled safely according to current behavior

## Scope
- identify the smallest stable seam around `confirm_external_payment_record`
- add tests around:
  - first successful confirmation
  - duplicate confirmation
  - stability of already confirmed state
  - invalid/missing payment record path if supported by current function behavior
- document what remains out of scope

## Out of scope
- changing payment provider webhook handling
- redesigning payment status model
- changing finalization orchestration
- UI/admin flows for payment management
- refactoring the whole billing subsystem

## Constraints
- keep tests deterministic
- avoid live provider/network dependencies
- protect current behavior rather than redesign it
- do not silently “improve” semantics inside the same task unless a bug is explicitly scoped

## Risks
- duplicate processing guard may depend on subtle DB state assumptions
- tests may accidentally become too integration-heavy
- invalid/missing record behavior may be inconsistent or historically shaped
- false confidence may appear if only the happy path is tested

## Acceptance criteria
- tests for `confirm_external_payment_record` exist
- first confirmation behavior is covered
- duplicate confirmation behavior is covered
- `just_confirmed` semantics are covered
- already-confirmed stability is covered
- duplicate-path note mutation is documented and protected as current behavior
- intentionally uncovered billing/idempotency gaps are documented

## Validation
Manual checks:
- verify tests target the real confirmation seam
- verify duplicate path does not mutate state incorrectly
- verify tests are rerunnable and deterministic
- verify no live provider dependency exists

## Deliverables
- idempotency tests for `confirm_external_payment_record`
- short note on what they protect
- explicit list of remaining billing/idempotency gaps
- suggested next billing hardening step
