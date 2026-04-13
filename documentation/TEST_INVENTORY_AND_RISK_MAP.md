# TEST INVENTORY AND RISK MAP

Date: 2026-03-19
Method: repository inspection, test-file review, domain/risk mapping
Status: completed

## Summary

The repository has a small real test surface and now a centralized `tests/` tree.
The current files under `tests/` are a mix of:
- tiny pure-logic checks;
- manual smoke scripts;
- integration-sensitive scripts that touch real DB/runtime services;
- one small pytest-style smoke file.

This means the project has some useful regression signals, but not a mature automated safety net.

## What exists now

Confirmed test files under `tests/`:
- `tests/test_access_logic.py`
- `tests/test_access_reminders.py`
- `tests/test_crypto_pay.py`
- `tests/test_db.py`
- `tests/test_manual_payments.py`
- `tests/test_region_integrity.py`
- `tests/test_security_smoke.py`
- `tests/test_subscription.py`
- `tests/test_support_storage.py`
- `tests/test_xui.py`

What is still missing structurally:
- no `pytest.ini`, `tox.ini`, `pyproject.toml`, or CI test workflow;
- no explicit coverage tooling;
- no clear separation between unit, integration, and manual smoke tests.

## Test-by-test inventory

### `tests/test_access_logic.py`

- type: small unit-style logic check
- touches:
  - access status classification
- runtime dependency:
  - config values for admin ids
- confidence:
  - medium for the narrow function it checks
- note:
  - useful as a fast guardrail, but only for one pure decision function

### `tests/test_access_reminders.py`

- type: mixed unit/integration-light test
- touches:
  - reminder classification
  - reminder delivery result handling
  - Telegram error-path behavior with fake bot stubs
- runtime dependency:
  - no live Telegram or DB required in the file itself
- confidence:
  - medium
- note:
  - one of the better isolated tests in the repo

### `tests/test_crypto_pay.py`

- type: unit-style protocol/security test
- touches:
  - webhook signature verification
  - freshness window logic
  - invoice payload parsing
- runtime dependency:
  - none
- confidence:
  - medium to high for the covered helper methods
- note:
  - strong narrow protection around critical webhook validation primitives

### `tests/test_db.py`

- type: manual smoke / DB integration script
- touches:
  - user creation
  - trial activation
  - active-trial query path
- runtime dependency:
  - live PostgreSQL and working config
- confidence:
  - low as automated protection
- note:
  - useful for operator smoke checks, weak as repeatable regression protection

### `tests/test_manual_payments.py`

- type: manual smoke / DB-heavy integration script
- touches:
  - manual payment record lifecycle
  - confirm / reject / cancel / expire flows
  - access expiry changes after confirmation
- runtime dependency:
  - live PostgreSQL and project runtime wiring
- confidence:
  - medium for exploratory smoke, low for automation
- note:
  - valuable because it touches a high-risk domain, but currently not shaped as a stable automated suite

### `tests/test_region_integrity.py`

- type: manual ops smoke script
- touches:
  - VPN region integrity
  - panel URL/login cross-check logic
- runtime dependency:
  - live VPN/XUI environment
- confidence:
  - low as regression protection
- note:
  - important operational diagnostic, not a safe unit/integration test layer

### `tests/test_security_smoke.py`

- type: small pytest-style smoke file
- touches:
  - HTML escaping in user-facing text
  - corrupt legacy support-storage recovery
- runtime dependency:
  - local temp dir only
- confidence:
  - medium
- note:
  - this is the closest file to a normal automated smoke test module

### `tests/test_subscription.py`

- type: manual external-service smoke script
- touches:
  - Telegram channel subscription check
- runtime dependency:
  - live Telegram Bot API and valid token
- confidence:
  - low as regression protection
- note:
  - useful for operational verification, weak for CI-like automation

### `tests/test_support_storage.py`

- type: manual DB integration script
- touches:
  - support ticket lifecycle
  - history trimming
  - admin assignment
  - admin reply
  - reopen flow
  - retention pruning
- runtime dependency:
  - live PostgreSQL, support storage bootstrap, support bot config
- confidence:
  - medium for smoke depth, low for automation maturity
- note:
  - one of the most important existing checks because support is a live production contour

### `tests/test_xui.py`

- type: manual external integration smoke script
- touches:
  - XUI login
  - VPN client provisioning
  - DB callback linkage
- runtime dependency:
  - live XUI panels and DB
- confidence:
  - low as regression protection
- note:
  - operationally important, but dangerous to treat as routine automated test coverage

## Coverage by domain

### Auth / session

- current coverage:
  - no explicit tests found for dashboard login, Telegram verify-code flow, session lifecycle, or admin auth boundaries
- posture:
  - weak

### User access / access status

- current coverage:
  - `tests/test_access_logic.py`
  - part of `tests/test_access_reminders.py`
  - part of `tests/test_db.py`
- posture:
  - partial

### Subscriptions

- current coverage:
  - indirect coverage through `tests/test_access_logic.py`
  - indirect/live smoke through `tests/test_manual_payments.py`
  - `tests/test_subscription.py` checks Telegram-channel subscription, not payment subscription lifecycle
- posture:
  - weak to partial

### Payments

- current coverage:
  - `tests/test_crypto_pay.py`
  - `tests/test_manual_payments.py`
- posture:
  - partial
- note:
  - primitives are covered better than end-to-end payment finalization

### Support / tickets

- current coverage:
  - `tests/test_support_storage.py`
  - partial corrupt-file fallback in `tests/test_security_smoke.py`
- posture:
  - partial

### Dashboard backend / API

- current coverage:
  - no explicit API tests found
  - no endpoint-level tests found for `dashboard` or `dashboard/ui` integration paths
- posture:
  - weak

### Панель управления UI integration points

- current coverage:
  - no frontend or API-contract tests found
- posture:
  - weak

### VPN / XUI integration

- current coverage:
  - `tests/test_xui.py`
  - `tests/test_region_integrity.py`
- posture:
  - partial operational smoke only

### Reminders / watchdog / background jobs

- current coverage:
  - `tests/test_access_reminders.py`
- posture:
  - partial
- note:
  - watchdog itself has no explicit test found in this pass

### DB schema / migrations / cross-component persistence

- current coverage:
  - live smoke around real DB paths in `tests/test_db.py`, `tests/test_support_storage.py`, `tests/test_manual_payments.py`
- posture:
  - weak to partial
- note:
  - persistence is touched, but not through isolated migration or repository-level tests

## High-risk / low-protection flows

### 1. Dashboard auth and admin session flow

- why risk is high:
  - gateway into the admin control plane
  - mixes `dashboard`, `support_bot`, Telegram verification, session storage, and runtime config
- current protection:
  - no explicit tests found

### 2. Payment finalization to access sync

- why risk is high:
  - money path plus entitlement change
  - touches DB, subscription state, referral bonus logic, and VPN expiry sync
- current protection:
  - partial primitives only
  - no explicit focused test found for `bot.payment_flow.finalize_subscription_payment`

### 3. VPN provisioning and expiry sync

- why risk is high:
  - depends on live XUI panels and region-specific behavior
  - mistakes can break real user access
- current protection:
  - manual smoke only

### 4. Dashboard API and `dashboard/ui` contract

- why risk is high:
  - `dashboard/ui` is now the main admin UI
  - backend/API still lives in `dashboard`
  - contract drift can silently break admin operations
- current protection:
  - no explicit API or contract tests found

### 5. Manual payment review flow

- why risk is high:
  - live operational path
  - support/admin action directly affects paid access
- current protection:
  - one useful smoke script, but not a stable automated suite

### 6. Support queue and ticket mutation flow

- why risk is high:
  - live user-facing support contour
  - state changes, trimming, assignment, close/reopen behavior
- current protection:
  - better than many other areas, but still mostly integration-smoke style

### 7. Watchdog / alerting / service health reactions

- why risk is high:
  - ops visibility and incident response depend on it
- current protection:
  - no explicit watchdog test found in this pass

## Practical regression risk ranking

### Highest risk

- dashboard auth/session and admin login verification
- payment finalization plus VPN expiry sync
- dashboard API to `dashboard/ui` integration contract
- live VPN/XUI provisioning and mutation flows

### High risk

- manual payment review lifecycle
- support ticket storage and admin operations
- watchdog / service-health notification flows

### Medium risk

- access reminder logic
- access-status classification helpers
- Crypto Pay webhook helper logic
- HTML escaping and corrupted legacy support file fallback

## What should not be changed casually

- `bot.payment_flow`
- `bot.manual_payments`
- `bot.vpn_api`
- `dashboard.services`
- `dashboard.v2_data`
- `support_bot.storage`
- admin auth/session code in `dashboard`
- runtime-sensitive ops flows around reminders/watchdog

These areas either have weak protection, heavy live dependencies, or both.

## Recommended next hardening targets

### 1. Dashboard auth/session smoke coverage

Add focused tests for:
- login credential check
- verify-code flow
- session creation/expiry
- protected-route access expectations

### 2. Payment finalization contract tests

Add focused tests for:
- `finalize_subscription_payment`
- subscription activation
- payment status transitions
- referral-bonus side effects
- sync-failed behavior without breaking entitlement update

### 3. Dashboard API contract smoke tests

Add focused tests for:
- key `dashboard/api/v2/*` endpoints used by `dashboard/ui`
- stable payload shape for overview, users, payments, support

### 4. VPN/XUI integration seam tests

Add tests that mock XUI client behavior for:
- successful login/provision
- failed login
- expiry sync failure
- region-specific panel selection

### 5. Support storage regression tests

Move strongest parts of `tests/test_support_storage.py` toward repeatable isolated tests with controlled DB fixtures.

## Strategic conclusion

The project is not test-empty, but it is underprotected in the places that matter most for safe feature work.

Current reality:
- narrow helper logic has some decent protection;
- critical product flows are covered mostly by manual smoke scripts or live integrations;
- admin/API contract risk is materially higher than the current test surface suggests.

The next safe engineering move is not “increase test count”.
It is to strengthen tests around the highest-risk flows first.
