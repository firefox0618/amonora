# TASK 045 RESULT — Post-payment access verification hardening

## What changed

`finalize_subscription_payment(...)` now performs an explicit post-payment verification pass instead of treating payment activation as the end of the flow.

## Healthy vs unhealthy outcomes

Healthy:
- access expiry exists
- VPN sync did not fail
- stale repair marker is cleared

Explicit failure reasons now persisted:
- `post_payment_access_incomplete`
- `post_payment_sync_failed`

## What was intentionally not added

- `post_payment_no_devices`

Reason:
- current product flow does not prove that every newly paid user must already have a device at finalization time
- auto-marking that state now would risk false positives

## Validation

Updated tests:
- `tests/test_payment_finalization.py`

Covered paths:
- successful payment finalization
- sync failure after payment
- missing access expiry after payment activation
