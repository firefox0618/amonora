# TASK 066 — Repair source / outcome normalization

## Status
Done

## Goal
Separate repair event source, outcome, and reason so repair history is easier to read and admin surfaces do not treat every event as if it had a failure reason.

## Why
After `065`, canonical repair reasons and labels were already stable, but real payloads still showed a semantic gap:
- successful manual repair events could surface `manual_repair` as if it were a reason
- guard-path events like `manual_repair_no_devices` looked like generic failures instead of explicit skips

That made repair history harder to interpret and blurred three different concepts:
- where the repair came from
- how it ended
- why it failed or was skipped

## Scope
Small normalization pass only:
- no DB migration
- no repair flow redesign
- no new automation logic
- serialize clearer event semantics on top of existing rows

## Implementation
- extended `bot/repair_reasons.py` with:
  - `repair_source`
  - `repair_outcome`
  - event-level reason normalization
- updated dashboard serializers to expose:
  - `source`
  - `source_label`
  - `outcome`
  - `outcome_label`
- normalized manual guard-path repair events to `skipped`
- kept `result` in payloads for compatibility, but aligned it with normalized outcome
- updated user detail and payment-linked UI to show source/outcome separately from reason

## Canonical model

### Repair source
- `post_payment`
- `manual`
- `auto`
- `unknown`

### Repair outcome
- `success`
- `failed`
- `skipped`
- `unknown`

## Acceptance criteria
- repair history clearly distinguishes source vs outcome vs reason
- success events no longer expose pseudo-reasons like `manual_repair`
- guard-path events such as `no devices` serialize as `skipped`
- existing repair flows keep working

## Validation
- backend/unit tests for source/outcome normalization
- dashboard repair payload tests
- payment-linked context payload checks
- frontend type alignment
