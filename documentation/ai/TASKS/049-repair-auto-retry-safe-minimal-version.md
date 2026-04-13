# TASK 049 — Repair auto-retry (safe minimal version)

## Status
Completed

## Goal
Reduce manual VPN repair load by introducing one safe automatic retry for fresh sync failures, without adding a background worker or hiding final failures.

## Why
The system already:
- detects VPN sync failures
- marks `vpn_repair_needed`
- allows manual repair
- stores repair event history

Some sync failures are still likely transient. A second immediate attempt is cheaper than forcing every case into manual follow-up.

## Scope
Strictly minimal:
- one additional retry only
- only inside fresh payment/manual-repair flows
- explicit event logging for auto attempts
- no queue, cron, worker, or recursion

## Implementation
- added `sync_user_vpn_access_with_single_retry(...)` in `bot/payment_flow.py`
- reused the helper in:
  - `finalize_subscription_payment(...)`
  - `repair_user_vpn_access(...)`
- auto-attempt events are stored as:
  - `success / auto_repair_success`
  - `failed / auto_repair_failed`

## Constraints kept
- guard paths without access/devices are unchanged
- failed auto-retry does not clear the repair marker
- successful auto-retry clears stale repair-needed state
- no loop and no hidden background retry behavior

## Validation
- update backend tests for payment finalization and manual repair
- verify no regression in existing repair marker behavior

