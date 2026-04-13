# TASK 052 — Payment/access repair reason normalization

## Status
Completed

## Goal
Normalize repair reasons so admin-facing payment/access/VPN signals stay consistent and easier to group in overview, user detail, and future alerts.

## Scope
Small normalization pass only:
- inventory current reasons
- define canonical names
- update new writes to use canonical names
- normalize legacy aliases on read

## Implementation
- added canonical reason module:
  - `bot/repair_reasons.py`
- switched new manual-repair writes to:
  - `manual_repair_sync_failed`
  - `manual_repair_no_access`
  - `manual_repair_no_devices`
- preserved read compatibility for old values through normalization helper
- overview, payment context, and user detail now consume normalized reasons

## Constraints kept
- no behavior redesign
- no schema migration
- no alert taxonomy expansion

