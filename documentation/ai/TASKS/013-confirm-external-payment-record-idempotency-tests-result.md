# TASK 013 RESULT — confirm_external_payment_record idempotency tests

## Status
Completed

## Outcome

The payment confirmation idempotency boundary now has focused tests:

- `tests/test_confirm_external_payment_record.py`

## What is now protected

- first confirmation marks the payment record as `confirmed`
- first confirmation sets `confirmed_at`
- first confirmation returns `just_confirmed = True`
- duplicate confirmation returns `just_confirmed = False`
- duplicate confirmation does not overwrite `confirmed_at`
- missing record returns `(None, False)`
- note mutation on first confirm is covered
- note mutation on duplicate confirm is covered as current contract behavior

## Important contract note

The current guard behaves as follows:

- it prevents duplicate confirmation from acting like a fresh confirmation
- it keeps already confirmed records stable with respect to `payment_status` and `confirmed_at`
- it still allows `note` mutation on duplicate confirm

This means the idempotency boundary protects against duplicate finalization entry, but does not make the record fully immutable.

## What is still not covered

- webhook transport behavior
- Telegram Stars and Crypto Pay end-to-end event flows
- coupling between confirmation and downstream orchestration in one combined seam
- provider-specific payload variation
- full DB-backed integration behavior for this path

## Verification

Executed:

- `./venv/bin/python -m unittest -q tests.test_confirm_external_payment_record`

Result:

- `Ran 5 tests`
- `OK`

## Best next hardening step

- `dashboard/api/v2/*` contract smoke
