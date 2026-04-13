# TASK 130 — Control error triggers for nodes, services, and users

## Status
Completed

## Goal
Add safe automatic control-plane triggers for node failures, service failures, and user access incidents, using the existing `Amonora Control` event log and delivery flow.

## Why
- the project already has manual status/problem surfaces and event delivery, but active incidents still depend too much on an operator opening the dashboard or control bot at the right time;
- node/runtime degradation, local service failures, and unresolved user repair states should escalate into `Amonora Control` automatically;
- the existing 5-minute reminder/trigger worker is already the safe place for periodic scans without introducing a new service.

## Scope
- extend the existing `amonora-access-reminders` worker with periodic incident scanning;
- emit deduped `Amonora Control` events for:
  - degraded/down nodes,
  - non-active local services,
  - users stuck in `vpn_repair_needed`;
- resolve prior incident events when the entity recovers;
- add focused tests for incident classification and scan output;
- update feature/ops/control-bot documentation and AI state.

## Out of scope
- changing the user-facing product flow;
- changing VPN provisioning logic;
- introducing a new monitoring stack, daemon, or third-party alerting system;
- changing dashboard/server runtime paths or service unit names.

## Constraints
- existing active flows for payments, access, devices, support, and dashboard operations must keep working unchanged;
- incident delivery must use the current `ControlNotificationEvent` + `create_control_event` seams;
- new alerts must be deduped and not spam every 5 minutes;
- recovery should clear prior unresolved incidents safely.

## Acceptance criteria
- a 5-minute worker run emits node alerts when a node becomes degraded/down and resolves them on recovery;
- the same worker emits service alerts when a monitored local service stops being `active` and resolves them on recovery;
- the same worker emits user-access alerts when a user remains in `vpn_repair_needed` and resolves them on recovery;
- focused tests cover incident classification and recovery paths without requiring live Telegram or SSH.

## Validation
- `./venv/bin/python -m unittest tests.test_control_error_triggers tests.test_access_reminders`
- `./venv/bin/python -m py_compile ops/access_reminders.py ops/control_error_triggers.py`
