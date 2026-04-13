# TASK 037 — VPN repair event log

## Status
Completed

## Goal
Persist and surface a minimal history of manual VPN repair attempts so admins can see what was tried, when, and whether it succeeded.

## Why
The system already supports:

- persistent `repair-needed` state
- visible repair warning in `dashboard_v2`
- manual `Repair VPN` action from user detail

What was still missing:

- history of repair attempts
- visibility into repeated failures
- a simple support/debugging trail for manual repair actions

## Scope
- add a minimal persistent event model
- record one event per manual repair attempt
- expose recent events through the existing user detail payload
- show recent events in `dashboard_v2` user detail

## Out of scope
- analytics
- retry counters
- alerts
- bulk repair history
- queue-based repair workflows
- broad audit redesign

## Acceptance criteria
- manual repair writes an event
- both success and failure are recorded
- recent events are visible in user detail
- normal flows remain unchanged

## Validation
- backend service tests:
  - successful repair writes a success event
  - failed repair writes a failed event
  - no-devices guard writes a failed event
  - user detail includes recent repair events
- targeted backend test run:
  - `./venv/bin/python -m unittest -q tests.test_dashboard_vpn_repair tests.test_payment_finalization`

