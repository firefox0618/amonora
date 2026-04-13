# TASK 159 — Paid device-slot add-ons result

## Status
Completed

## What changed
- added persistent `DeviceSlotEntitlement` storage in `backend/core/models.py` plus schema support in `backend/core/schema.py`;
- introduced shared device-slot helpers in `bot/utils/device_slots.py` and switched access/device-limit calculations to use active entitlements instead of a hardcoded `3`;
- updated `@amonora_bot` device UX:
  - the devices screen now shows the real current limit;
  - device-limit reach now offers `Купить +1 устройство за 49 ₽` instead of only a hard stop;
  - add-on purchase is restricted to active paid users and capped at `8` effective devices total;
- reused existing payment seams for the new product type `device_slot_addon`:
  - `Platega` auto checkout;
  - manual SBP review;
  - balance-only immediate activation when the internal balance fully covers the add-on price;
- split payment finalization by product type, so add-on confirmations create entitlements and mark `device_slot_activation` without extending the subscription itself;
- updated dashboard/control surfaces to show product-aware payment labels and dynamic `devices/max_devices` context instead of `x/3`;
- added add-on expiry handling to the shared `ops/access_reminders.py` worker, while intentionally leaving existing devices untouched if the downgraded limit is exceeded after expiry.

## Files changed
- `backend/core/models.py`
- `backend/core/schema.py`
- `bot/config.py`
- `bot/db.py`
- `bot/payment_flow.py`
- `bot/manual_payments.py`
- `bot/platega_flow.py`
- `bot/utils/access.py`
- `bot/utils/device_slots.py`
- `bot/utils/texts.py`
- `bot/keyboards/devices.py`
- `bot/keyboards/tariffs.py`
- `bot/handlers/devices.py`
- `bot/handlers/tariffs.py`
- `dashboard/services.py`
- `dashboard/v2_data.py`
- `dashboard/ui/src/lib/types.ts`
- `dashboard/ui/src/app/(dashboard)/users/page.tsx`
- `dashboard/ui/src/app/(dashboard)/payments/page.tsx`
- `control_bot/storage.py`
- `control_bot/queries.py`
- `ops/access_reminders.py`
- `tests/test_bot_device_limits.py`
- `tests/test_payment_finalization.py`
- `tests/test_dashboard_payment_actionability.py`
- `tests/test_dashboard_v2_users_payload.py`
- `tests/test_control_queries.py`
- `documentation/DOMAIN.md`
- `documentation/FEATURES.md`
- `documentation/ai/STATE.md`

## Validation
- `./venv/bin/python -m py_compile bot/db.py bot/payment_flow.py bot/manual_payments.py bot/platega_flow.py bot/handlers/tariffs.py bot/handlers/devices.py bot/keyboards/devices.py bot/keyboards/tariffs.py bot/utils/texts.py dashboard/services.py dashboard/v2_data.py control_bot/storage.py control_bot/queries.py ops/access_reminders.py`
- `./venv/bin/python -m unittest tests.test_bot_device_limits tests.test_payment_finalization tests.test_dashboard_payment_actionability tests.test_control_queries tests.test_dashboard_v2_users_payload tests.test_bot_copy_updates tests.test_manual_payments tests.test_access_reminders tests.test_bot_payment_handlers`

## Follow-up notes
- the safe v1 intentionally does not auto-delete or auto-disable existing devices when an add-on expires and the user remains above the downgraded limit;
- `Telegram Stars` is still subscription-only and is not used for the new add-on product;
- production rollout still requires the usual deploy + migration/app restart step outside this repo-side implementation result.
