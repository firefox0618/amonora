# TASK 150 — Dashboard support reply structured error

## Status
Completed

## Goal
Stop the control-center support reply flow from leaking an HTML 500 page into `dashboard/ui` when Telegram rejects delivery.

## Why
Operators should get a clear actionable error in the support screen, not a generic frontend parsing failure with raw HTML.

## Context
Relevant docs and code areas:
- `documentation/RUNBOOK.md`
- `documentation/FEATURES.md`
- `documentation/ai/STATE.md`
- `dashboard/main.py`
- `dashboard/services.py`
- `dashboard/ui/src/lib/api.ts`
- `tests/test_dashboard_acr_fixes.py`
- `tests/test_dashboard_api_v2_support_contract.py`

## Current behavior
`dashboard/ui` posts support replies through `/api/proxy/dashboard/api/v2/support/{ticket_user_id}/reply`.  
If Telegram rejects the outbound message, `dashboard` raises an unhandled exception and FastAPI returns an HTML 500 page.  
The Next.js client then fails JSON parsing and shows `Не удалось обработать ответ сервера: <!DOCTYPE html> ...`.

## Desired behavior
Support reply failures caused by Telegram delivery should be converted into structured business errors:
- `dashboard/api/v2/*` should return JSON error payloads;
- legacy `/dashboard/support/*` should redirect back with an operator-visible error;
- operator copy should explain the likely cause, such as the user blocking `@amonora_support_bot`.

## Scope
Included:
- normalize Telegram support-delivery failures in `dashboard.services.send_support_reply`;
- guard both the v2 API route and the legacy reply route;
- add focused regression tests for the service seam and the v2 JSON contract;
- update reliability docs/state.

## Out of scope
- redesigning support delivery into a durable outbox;
- changing support ticket storage semantics;
- changing the `dashboard/ui` support UX beyond receiving the structured error.

## Constraints
- preserve current support ticket storage and audit flow;
- do not change runtime paths, ports, or service names;
- keep compatibility with legacy `/dashboard/support/*`.

## Risks
- support reply remains dependent on Telegram as an external transport;
- over-broad exception handling could hide genuine programming errors if not limited to known Telegram delivery failures.

## Acceptance criteria
- blocked/failed Telegram delivery no longer produces an HTML traceback in `dashboard/ui`;
- operators receive a readable business error instead;
- service-level tests cover the blocked-bot path;
- API contract tests cover JSON error response for reply failure.

## Validation
- `./venv/bin/python -m py_compile dashboard/services.py dashboard/main.py tests/test_dashboard_acr_fixes.py tests/test_dashboard_api_v2_support_contract.py`
- `./venv/bin/python -m unittest tests.test_dashboard_acr_fixes.DashboardAcrFixesTests.test_send_support_reply_rejects_missing_ticket_before_telegram_delivery tests.test_dashboard_acr_fixes.DashboardAcrFixesTests.test_send_support_reply_surfaces_blocked_support_bot_as_value_error tests.test_dashboard_api_v2_support_contract.DashboardApiV2SupportContractSmokeTests.test_dashboard_api_v2_support_reply_returns_json_error_when_delivery_fails`

## Deliverables
- support reply error normalization in backend routes/services;
- regression tests for the blocked-bot and JSON-contract paths;
- updated feature/state documentation.
