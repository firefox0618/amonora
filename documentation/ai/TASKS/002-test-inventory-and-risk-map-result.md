# TASK 002 RESULT — Test inventory and risk map

## Status
Completed

## Outcome

A canonical test/risk document was created:

- `documentation/TEST_INVENTORY_AND_RISK_MAP.md`

## What was confirmed

- at the time of the original audit there was no centralized `tests/` tree;
- at the time of the original audit most project test files lived in the repo root;
- most of the current test surface is a mix of:
  - manual smoke scripts
  - live DB integration checks
  - live Telegram/XUI operational checks
  - a few narrow pure-logic checks
- there is no visible pytest/coverage/CI-style test harness in the repo structure from this pass.

## Main risk conclusion

The project is not test-empty, but critical flows are underprotected.

Highest-risk weakly protected areas:
- dashboard auth/session
- payment finalization plus VPN expiry sync
- dashboard API contract for `dashboard_v2`
- live VPN/XUI provisioning and mutation flows

## Recommended next hardening targets

- dashboard auth/session smoke tests
- payment finalization contract tests
- `dashboard/api/v2/*` contract smoke tests
- mocked XUI seam tests
- stronger support storage regression tests

## Follow-up

- use this map before making risky changes in payment, VPN, dashboard, and support flows;
- prefer small hardening tasks over broad test rewrites;
- treat existing root test scripts as mixed smoke assets, not as proof of mature automated coverage.
