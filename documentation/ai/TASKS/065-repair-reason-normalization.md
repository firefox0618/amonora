# TASK 065 — Repair reason normalization

## Status
Done

## Goal
Normalize `vpn_repair_reason` usage so repair-related signals stay consistent across backend, overview, user detail, payments context, and support-facing workflows.

## Why
The project already had a working repair marker and repair history, but reason strings were starting to split across:
- canonical reasons
- legacy aliases
- raw codes shown directly in UI

That increased operator noise and made repair history harder to read.

## Scope
Small normalization pass only:
- keep runtime semantics unchanged
- keep the existing canonical reason set
- expose human-readable labels together with canonical reason codes
- normalize legacy aliases at serialization boundaries

## Out of scope
- repair flow redesign
- new repair automation
- source/outcome normalization (`066`)
- overview dedup/simplification (`067`)

## Implementation
- expanded `bot/repair_reasons.py` into the canonical source for:
  - persistent repair reasons
  - event-only repair reasons
  - legacy alias normalization
  - human-readable labels
- extended dashboard/user/payment payloads with:
  - `reason_label`
  - `vpn_repair_reason_label`
  - `last_repair_reason_label`
- updated frontend surfaces to prefer labels over raw reason codes

## Acceptance criteria
- one canonical set of repair reasons remains in code
- legacy aliases normalize to canonical reasons
- user-facing admin surfaces show readable labels
- existing behavior stays unchanged

## Validation
- backend/unit tests for normalization and payload serialization
- existing dashboard repair/overview tests updated
- frontend typecheck/build
