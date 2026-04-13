# TASK 033 — VPN sync failed -> repair-needed state

## Status
Completed

## Goal
Make VPN sync failures explicit and persistent by introducing a `repair-needed` state instead of silently allowing entitlement and VPN state to diverge.

## Scope
- payment finalization path
- minimal persistence on `User`
- backend/admin visibility
- focused payment-flow tests

## Deliverables
- persistent repair-needed marker
- updated payment finalization logic
- backend visibility in user detail payload
- task result note
