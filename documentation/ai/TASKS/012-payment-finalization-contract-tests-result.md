# TASK 012 RESULT — Payment finalization contract tests

## Status
Completed

## Outcome

The first payment finalization contract test layer was implemented:

- `tests/test_payment_finalization.py`

## What is now protected

- successful finalization calls activation, expiry readback, and VPN sync in the expected order
- unknown tariff input is rejected safely
- activation failure prevents expiry readback and VPN sync
- soft VPN sync failure is surfaced through `sync_failed` without discarding the successful entitlement result
- expiry read failure is surfaced explicitly after activation
- repeated direct calls replay the orchestration flow, documenting that `finalize_subscription_payment` is not itself idempotent

## Important contract note

The tests intentionally document the current boundary of responsibility:

- payment confirmation idempotency lives outside `finalize_subscription_payment`
- the orchestration function itself is not protected against direct repeated invocation

This is treated as current system truth, not silently hidden by the test layer.

## What is still not covered

- real webhook transport
- provider-specific payload variations
- Telegram Stars end-to-end flow
- manual payment admin/UI flow
- real database persistence through the full payment path
- live XUI/VPN side effects
- payment-record idempotency guard behavior in `confirm_external_payment_record`

## Verification

Executed:

- `./venv/bin/python -m unittest -q tests.test_payment_finalization`

Result:

- `Ran 6 tests`
- `OK`

## Best next payment hardening step

- add focused tests around `confirm_external_payment_record` as the idempotency boundary
- then move to `dashboard/api/v2/*` contract smoke
