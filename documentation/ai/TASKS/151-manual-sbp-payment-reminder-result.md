# TASK 151 RESULT — Manual SBP payment reminder in dashboard

## Outcome
Operators can now send a dedicated reminder from `Панель управления -> Транзакции` for open manual `СБП` requests. The user receives a targeted follow-up in the main bot with direct actions to mark the payment as submitted, re-check status, cancel the request, or go to support for payment details.

## What changed
- `dashboard/services.py` now exposes a safe reminder seam for open `sbp_manual` records only;
- the payment payload now carries `can_send_reminder`, so the control-center UI can show the action only when the record is eligible;
- `dashboard/main.py` now serves `POST /dashboard/api/v2/payments/{record_id}/remind`;
- `dashboard/ui` payment detail shows `Напомнить об оплате` and refreshes the payments slice after success;
- `bot/utils/texts.py` and `bot/keyboards/tariffs.py` now provide the reminder copy and dedicated inline keyboard for the user.

## Validation completed
- `./venv/bin/python -m py_compile bot/keyboards/tariffs.py bot/utils/texts.py dashboard/services.py dashboard/main.py tests/test_dashboard_acr_fixes.py tests/test_dashboard_provider_payment_sync.py tests/test_dashboard_payment_actionability.py`
- `./venv/bin/python -m unittest tests.test_dashboard_acr_fixes.DashboardAcrFixesTests.test_send_manual_payment_reminder_delivers_to_open_sbp_manual_record tests.test_dashboard_acr_fixes.DashboardAcrFixesTests.test_send_manual_payment_reminder_rejects_non_open_manual_sbp_record tests.test_dashboard_provider_payment_sync.DashboardProviderPaymentSyncTests.test_dashboard_api_v2_payments_remind_calls_manual_reminder tests.test_dashboard_payment_actionability.DashboardPaymentActionabilityTests`

## Residual risks
- delivery still depends on the user not blocking the main bot;
- there is no reminder cooldown yet, so repeated sends remain a deliberate operator action.
