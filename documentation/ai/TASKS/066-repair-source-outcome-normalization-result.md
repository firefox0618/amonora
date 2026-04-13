# TASK 066 — Repair source / outcome normalization result

## Status
Done

## What changed
- repair event payloads now expose:
  - `source`
  - `source_label`
  - `outcome`
  - `outcome_label`
- persistent repair state now also exposes source metadata
- manual repair guard paths now serialize as `skipped`, not generic `failed`
- successful manual repair events no longer surface `manual_repair` as if it were a failure reason

## Resulting behavior
- admin can now read repair history as:
  - where it came from
  - what happened
  - why it failed or was skipped, if applicable
- successful events may legitimately have:
  - source present
  - outcome present
  - no reason

## UI effect
- user detail repair history now shows:
  - outcome badge
  - source chip
  - reason only when it exists
- payment-linked user issue summary now includes:
  - repair source
  - normalized last repair outcome

## What did not change
- repair persistence model
- repair-needed marker behavior
- repair prioritization or escalation
- payment/access repair taxonomy from `065`

## Follow-up
- `067` should simplify overview duplication using the now-cleaner repair semantics
- `068` should keep backup/restore system status honest and compact
