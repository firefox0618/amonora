# TASK 063 — Guardrails for dangerous actions Result

## Result
Repair actions now have lightweight guardrails before execution instead of relying only on post-click backend rejection.

## Added protections
- disabled `Repair VPN` when user has no active access
- disabled `Repair VPN` when user has no devices
- disabled batch selection for invalid repair candidates
- added confirm step for batch repair

## Shared signals
- `can_repair`
- `repair_block_reason`

These signals now feed overview, user detail, and payment-linked context.
