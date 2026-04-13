# TASK 150 RESULT — Dashboard support reply structured error

## Outcome
The support reply flow in the control center no longer breaks with an HTML 500 page when Telegram rejects delivery. Operators now get a structured error that explains the user likely blocked `@amonora_support_bot` or Telegram rejected the message for another delivery reason.

## What changed
- `dashboard.services.send_support_reply` now converts `TelegramForbiddenError` and `TelegramBadRequest` into readable `ValueError` messages instead of letting the exception escape as an unhandled server error;
- `POST /dashboard/api/v2/support/{ticket_user_id}/reply` now returns `_api_error(..., 400)` for those business failures, preserving the JSON contract expected by `dashboard/ui`;
- legacy `POST /dashboard/support/{ticket_user_id}/reply` now redirects back with an error notice instead of failing hard with a 500 page;
- focused regression coverage was added for the blocked-support-bot path and the v2 JSON error contract.

## Validation completed
- `./venv/bin/python -m py_compile dashboard/services.py dashboard/main.py tests/test_dashboard_acr_fixes.py tests/test_dashboard_api_v2_support_contract.py`
- `./venv/bin/python -m unittest tests.test_dashboard_acr_fixes.DashboardAcrFixesTests.test_send_support_reply_rejects_missing_ticket_before_telegram_delivery tests.test_dashboard_acr_fixes.DashboardAcrFixesTests.test_send_support_reply_surfaces_blocked_support_bot_as_value_error tests.test_dashboard_api_v2_support_contract.DashboardApiV2SupportContractSmokeTests.test_dashboard_api_v2_support_reply_returns_json_error_when_delivery_fails`

## Residual risks
- support delivery still depends on Telegram and is not transactional with local history;
- operators can still encounter legitimate delivery failures, but they now surface as readable business errors instead of frontend parse failures.
