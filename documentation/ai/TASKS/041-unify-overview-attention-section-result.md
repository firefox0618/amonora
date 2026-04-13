# TASK 041 — Unify overview attention section Result

## Result
Completed.

## What changed
- Reworked the overview right rail into one coherent `Needs attention` section
- Kept the same existing signals, but grouped them into:
  - `Users`
  - `System`

## What did not change
- no new signals
- no backend payload changes
- no overview contract changes

## Validation
- `dashboard_v2` typecheck/build re-confirmed in Windows Node environment

## Effect
The overview attention layer now reads as one intentional product surface instead of two neighboring but separate blocks.
