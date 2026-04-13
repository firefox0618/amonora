# TASK 042 — Payment / support / access triage map

## Status
Completed

## Goal
Map the main manual-intervention hotspots across payment, support, and access flows, and identify the smallest next hardening/automation candidates with the highest practical value.

## Why
The project now already has:

- backup / restore groundwork
- VPN repair flow
- overview attention layer

The next strongest leverage point is not another UI polish step, but the place where operator time and product friction still accumulate:

- manual payment queue
- support backlog
- access issues after payment
- repeated repair/manual recovery

## Scope
- documentation-only mapping
- no runtime changes
- no UI implementation
- no new automation yet

## Acceptance criteria
- a canonical triage map exists
- manual hotspots are listed with visibility and operator path
- current operator-knowledge gaps are called out explicitly
- 1–2 next high-value hardening candidates are proposed

## Validation
- verify mapping against current payment/access/support code paths
- verify current visibility against dashboard/support/overview reality
- clearly separate confirmed current behavior from inferred next opportunities

