# Task 131 — Safe ACR Hardening for Payments, Support, and Nodes

## Context

The previous ACR pass identified a few remaining production risks that could still mislead operators or create partial system state:

- dashboard-confirmed non-manual payments used a narrower direct-extend path instead of the shared post-payment finalization orchestration;
- support queue counts still scanned the full ticket set instead of using DB-side aggregates;
- the control bot exposed a node action labeled `Resync`, while the backend only performed a safe status refresh / health-check pass;
- server migration still had a region-based fallback for devices without explicit source-node binding, which was unsafe for partial or mixed node ownership.

## Scope

Close the safe subset of those ACR items without broad rewrites:

- route confirmed non-manual dashboard payments through the shared payment finalization orchestration;
- move support queue counters to SQL aggregates;
- rename the control-bot node action to an honest refresh/status action and support the alias cleanly;
- make server migration conservative by skipping unbound devices into manual review and avoiding auto-maintenance on partial migration.

## Constraints

- no repo-wide refactor of the payment domain;
- no new destructive migration semantics for existing devices;
- no removal of existing working payment/support/node flows;
- changes must stay reversible and covered by tests.

## Acceptance criteria

- dashboard-confirmed non-manual payments invoke the shared payment finalization path;
- support queue counts no longer depend on full in-memory ticket scans;
- control bot no longer presents a fake `Resync` action when only refresh is available;
- migration skips unbound devices and reports manual review instead of pretending success;
- targeted tests cover the new behavior.

## Validation

- `python -m unittest` for targeted payment/support/control/node suites;
- extended regression suite for dashboard/control/support/payment contracts;
- `py_compile` on changed Python files;
- frontend typecheck because control-bot wording changes flow into operator UX expectations.
