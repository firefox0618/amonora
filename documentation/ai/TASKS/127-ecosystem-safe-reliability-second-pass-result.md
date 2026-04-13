# TASK 127 RESULT — Ecosystem safe reliability second pass

## Outcome
The second safe pass closed the remaining high-risk runtime seams that still threatened paying users, while preserving the current production architecture and active flows.

## What changed
- duplicate Telegram Stars delivery no longer replays subscription finalization or double-extends access;
- balance-aware payment creation and balance reserve/apply/release paths now serialize on the user row, reducing concurrent hold drift for mixed/manual payments;
- dashboard support reply now refuses to send when there is no local ticket and logs/escalates local-history save failure after Telegram delivery;
- device creation now distinguishes successful provisioning from failed credential delivery and tells the user how to recover without creating a duplicate device;
- focused regression tests now cover the Telegram Stars duplicate path, the post-provision delivery fallback, and the support-reply preflight guard.

## Validation completed
- `./venv/bin/python -m py_compile bot/handlers/tariffs.py bot/db.py bot/handlers/devices.py bot/utils/texts.py dashboard/services.py`
- `./venv/bin/python -m unittest tests.test_bot_payment_handlers tests.test_bot_device_delivery_fallback tests.test_dashboard_acr_fixes`
- `./venv/bin/python -m unittest tests.test_confirm_external_payment_record tests.test_payment_finalization tests.test_referral_balance tests.test_dashboard_vpn_repair`
- `./venv/bin/python -m unittest tests.test_bot_modes tests.test_bot_copy_updates tests.test_bot_devices_ui`
- `git diff --check`

## Residual risks
- support reply still cannot be made fully transactional across Telegram delivery and DB history without an explicit outbox/delivery-status layer;
- external payment deduplication is safer for the active user-bound flows, but a schema-level unique guarantee for historical external IDs still remains a separate migration task;
- node drift is substantially better handled by the current repair/reconcile paths, but real runtime drift can still depend on provider-side availability outside the Python control plane.
