# TASK 061 — Operator workflow shortcuts (fast actions)

## Status
Complete

## Goal
Reduce time-to-action for common admin operations by adding faster one-click shortcuts and reusing existing safe actions.

## Implemented scope
- quick navigation from overview attention items to user context
- quick navigation from support context to user/payment context
- inline `Repair VPN` from overview repair cards
- inline `Repair VPN` from payment-linked user context

## What was intentionally not added
- no new backend orchestration
- no destructive inline actions
- no batch execution yet
- no UI redesign

## Validation
- frontend typecheck/build
- manual review of overview, payments, and support action paths

## Deliverables
- faster operator shortcuts
- reuse of existing repair API in more relevant contexts
- result note
