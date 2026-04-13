# TASK 121 RESULT — Control Center Audit and Support Actionability

## Outcome
Task completed.

The control-center layer now has a dedicated `Audit log` screen in `dashboard/ui`, a new `/dashboard/api/v2/audit` payload, an explicit EKB time/role block in the topbar, and a safer support linked context that drives panel actions through the real internal `users.id`.

## Implemented changes
- added `get_v2_audit_payload()` and `/dashboard/api/v2/audit`;
- added `Audit` to v2 session navigation;
- added `dashboard/ui` audit page with filters, summary cards, and recent event stream;
- added support linked-user context builder for real user/profile/payment linkage;
- updated support detail quick actions to use safe existing user endpoints;
- added contract/unit coverage for the new audit route and support linked-context mapping.

## Validation
- `./venv/bin/python -m unittest tests.test_dashboard_api_v2_audit_contract tests.test_dashboard_support_linked_context tests.test_dashboard_api_v2_support_contract`
- `powershell.exe -ExecutionPolicy Bypass -NoProfile -Command "Set-Location '\\\\wsl.localhost\\Ubuntu\\home\\dextrmed\\projects\\amonora_bot\\dashboard\\ui'; & 'C:\\Program Files\\nodejs\\npm.cmd' run typecheck"`
- `./venv/bin/python -m compileall dashboard`

## Notes
- legacy `dashboard` was intentionally preserved because it remains an active backend/API seam;
- the task does not widen payment or VPN domain logic, it only improves operator visibility and actionability around the existing safe APIs.
