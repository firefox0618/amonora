# TASK 045 — Post-payment access verification hardening

## Status
Completed

## Goal
Immediately verify the most important access/VPN outcomes after payment confirmation so payment success does not silently diverge from real user access.

## Outcome

The post-payment seam in `bot/payment_flow.py` now explicitly treats finalization as a verification step:
- if access expiry is missing after activation, the flow marks `vpn_repair_needed` with `post_payment_access_incomplete`
- if VPN sync fails after activation, the flow marks `vpn_repair_needed` with `post_payment_sync_failed`
- successful path still clears stale repair markers

## Scope kept intentionally narrow

Included:
- explicit post-payment verification in `finalize_subscription_payment(...)`
- explicit post-payment repair reasons
- focused tests for success, sync-failure, and access-incomplete paths

Not included:
- device recreation logic
- retry engine
- broad billing redesign
- automatic `no devices after payment` marker, because that would be too assumption-heavy for the current flow
