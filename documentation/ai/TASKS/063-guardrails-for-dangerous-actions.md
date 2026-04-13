# TASK 063 — Guardrails for dangerous actions

## Status
Complete

## Goal
Prevent obviously invalid repair actions by surfacing lightweight guardrails before the operator clicks.

## Implemented scope
- repair eligibility is now derived from:
  - active access status
  - device presence
- invalid repair actions are disabled in:
  - overview repair shortcuts
  - overview batch repair selection
  - user detail
  - payment-linked user context
- batch repair now asks for confirmation before execution

## Guard rules
- no active access -> cannot repair
- no devices -> cannot repair

## Out of scope
- new permission model
- destructive confirmations everywhere
- RBAC redesign
- backend flow redesign

## Validation
- overview payload/unit tests
- overview contract update
- frontend typecheck/build
