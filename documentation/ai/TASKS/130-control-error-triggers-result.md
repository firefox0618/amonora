# TASK 130 RESULT — Control error triggers for nodes, services, and users

## Outcome
The existing 5-minute `amonora-access-reminders` worker now also scans operational incidents and raises deduped `Amonora Control` events for node degradation, key local service failures, and unresolved user access issues.

## What changed
- added a dedicated incident-classification layer for nodes, services, and aggregated user `vpn_repair_needed` issues;
- wired the current worker to emit control events for active incidents and recovery events when the same incident key returns to healthy state;
- kept the current reminder / trigger campaign flow unchanged and additive;
- expanded documentation so the worker is now described as both a user-trigger engine and an operational incident scanner;
- added focused tests for incident classification and recovery orchestration.

## Validation completed
- `./venv/bin/python -m py_compile ops/control_error_triggers.py ops/access_reminders.py`
- `./venv/bin/python -m unittest tests.test_control_error_triggers tests.test_access_reminders tests.test_access_reminders_triggers tests.test_control_queries`

## Residual risks
- node scanning still depends on the current SSH and remote-metrics path from `dashboard.services`, so provider-side reachability problems can still affect signal quality;
- service monitoring is tied to the explicitly enumerated unit list and should be revisited if new core units become operationally critical.
