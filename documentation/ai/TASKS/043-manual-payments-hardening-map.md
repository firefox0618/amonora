# TASK 043 — Manual payments hardening map

## Status
Completed

## Goal
Map the real manual payment flow and identify the smallest hardening steps that reduce manual queue friction, confirmation mistakes, and payment-to-access delays.

## Why
The system already has:
- payment finalization protection
- payment idempotency protection
- support and system attention surfaces
- visibility into repair-needed access problems

But manual payments still represent a high-friction operator path:
- they depend on human review
- they can delay access
- they can create support load
- they can hide small process inconsistencies

## Scope
Read-only mapping only:
- no runtime changes
- no UI changes
- no billing redesign

Mapped:
- where manual payments are created
- where they are reviewed
- where they are confirmed/rejected
- where access is activated after confirmation
- where delays, ambiguity, or repeated operator work happen

## Out of scope
- rewriting manual payments
- changing queue logic
- changing payment providers
- redesigning dashboard payments screen
- adding automation in this task

## Context
Relevant areas:
- `bot/manual_payments.py`
- `bot/handlers/tariffs.py`
- `bot/db.py`
- payment/admin review paths
- `dashboard`/`dashboard_v2` payment-related surfaces
- support-related flows where they intersect manual payments

Relevant docs:
- `documentation/DOMAIN.md`
- `documentation/FEATURES.md`
- `documentation/TEST_INVENTORY_AND_RISK_MAP.md`
- `documentation/ALERTS_ATTENTION_MAP.md`
- `documentation/ai/STATE.md`

## Deliverables
- canonical flow map in `documentation/MANUAL_PAYMENTS_FLOW_MAP.md`
- task result note
- updated `STATE.md`
