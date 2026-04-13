# TASK 151 — Manual SBP payment reminder in dashboard

## Status
Completed

## Goal
Add a dedicated operator action in `Панель управления -> Транзакции` that reminds users about open manual `СБП` payments.

## Why
Operators need a fast way to nudge users who opened a manual SBP payment but did not complete it, without manually searching for the user and composing a message.

## Context
Relevant docs and code areas:
- `documentation/FEATURES.md`
- `documentation/ai/STATE.md`
- `dashboard/main.py`
- `dashboard/services.py`
- `dashboard/ui/src/app/(dashboard)/payments/page.tsx`
- `dashboard/ui/src/lib/types.ts`
- `bot/keyboards/tariffs.py`
- `bot/utils/texts.py`

## Current behavior
Operators can review, reject, delete, sync, or change payment status, but there is no direct reminder action for a user who left a manual `СБП` request hanging.

## Desired behavior
For an open `sbp_manual` payment, the payment detail should show a `Напомнить об оплате` action.  
When triggered, the user receives a bot message that:
- reminds them about the open payment request;
- tells them to write to support if they need payment details again;
- lets them mark the request as paid, check status, or cancel it.

## Scope
Included:
- payment reminder backend action for open `sbp_manual` records;
- new reminder text and inline keyboard for the user;
- new button in `dashboard/ui` payment detail;
- focused regression tests and doc updates.

## Out of scope
- auto-scheduled reminder campaigns;
- reminders for provider payments;
- reminders for non-SBP manual methods.

## Constraints
- keep current payment-status flow intact;
- do not change runtime ports or service names;
- preserve existing user-side manual-payment callbacks.

## Risks
- reminder delivery still depends on the user being reachable in the main bot;
- operators can send multiple reminders manually, because this pass does not add cooldown/state tracking.

## Acceptance criteria
- open `sbp_manual` records expose a visible reminder action in payment detail;
- backend rejects reminder attempts for non-open or non-manual-SBP payments;
- user reminder message includes support and cancellation paths;
- regression tests cover the service path, endpoint contract, and payment payload flag.

## Validation
- `./venv/bin/python -m py_compile bot/keyboards/tariffs.py bot/utils/texts.py dashboard/services.py dashboard/main.py tests/test_dashboard_acr_fixes.py tests/test_dashboard_provider_payment_sync.py tests/test_dashboard_payment_actionability.py`
- `./venv/bin/python -m unittest tests.test_dashboard_acr_fixes.DashboardAcrFixesTests.test_send_manual_payment_reminder_delivers_to_open_sbp_manual_record tests.test_dashboard_acr_fixes.DashboardAcrFixesTests.test_send_manual_payment_reminder_rejects_non_open_manual_sbp_record tests.test_dashboard_provider_payment_sync.DashboardProviderPaymentSyncTests.test_dashboard_api_v2_payments_remind_calls_manual_reminder tests.test_dashboard_payment_actionability.DashboardPaymentActionabilityTests`

## Deliverables
- backend reminder action;
- user-facing reminder copy and keyboard;
- `dashboard/ui` action button;
- updated docs/state.
