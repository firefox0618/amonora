# TASK 126 — Ecosystem safe reliability second pass

## Status
Completed

## Goal
Close the remaining high-risk reliability seams from the production-safe ecosystem audit without breaking active user, payment, support, or VPN flows.

## Why
- duplicate Telegram Stars updates can still replay subscription finalization;
- payment creation and balance reservation still need stronger serialization for concurrent starts;
- support replies can still reach Telegram before the system verifies that the ticket exists locally;
- device provisioning can succeed while credential delivery fails, creating false "creation failed" support cases.

## Scope
- harden Telegram Stars payment confirmation handling against duplicate finalization;
- serialize balance-aware payment creation around the user row and apply the same lock on reserve/apply/release paths;
- make dashboard support reply refuse to send when no ticket exists and surface local-history save failure more clearly;
- separate successful device provisioning from post-provision credential delivery so users get a safe recovery path;
- add focused regression tests for the newly hardened seams.

## Out of scope
- production deploy;
- broad payment architecture rewrite;
- full support outbox implementation;
- destructive schema cleanup or historical deduplication.

## Constraints
- preserve existing production behavior for successful happy paths;
- no removal of working legacy/admin flows without fallback;
- keep changes small, reviewable, and reversible;
- prioritize correctness for active paying users over refactor quality.

## Acceptance criteria
- duplicate Telegram Stars delivery does not call subscription finalization twice;
- concurrent balance-aware payment starts serialize through a per-user DB lock;
- support reply does not deliver to Telegram when there is no local ticket to attach history to;
- device creation no longer reports a generic provisioning failure when provisioning succeeded but delivery failed;
- focused tests cover the new guards and existing critical flows still pass.

## Validation
- `./venv/bin/python -m unittest tests.test_confirm_external_payment_record tests.test_payment_finalization tests.test_dashboard_acr_fixes`
- `./venv/bin/python -m unittest tests.test_bot_payment_handlers tests.test_bot_device_delivery_fallback`
- `./venv/bin/python -m unittest tests.test_referral_balance tests.test_dashboard_vpn_repair`
- `./venv/bin/python -m py_compile bot/handlers/tariffs.py bot/db.py bot/handlers/devices.py dashboard/services.py`
