# TASK 123 — Control center ops completion

## Status
Completed

## Goal
Close the remaining operator-facing gaps from `amonora_control_tz_v4.md` so the active `dashboard/ui` control center covers the intended role model, repair actions, payment-state flow, server actions, and traffic/attention surfaces without falling back to legacy behavior.

## Why
- the shell redesign and audit/support linkage were already complete, but several points from the final control-center brief still lived as partial backend seams, partial UI affordances, or ungated role access;
- active operators need the new panel to be coherent under real roles, not just visually redesigned;
- the implementation must stay safe for existing users and avoid destructive rewrites of load-bearing backend seams.

## Scope
- finalize role-aware read/action boundaries for `owner`, `tech_admin`, and `support_admin` (`Менеджер`);
- expose `sync` and `deep repair` across the main user/support/payment operator contexts;
- expand payment handling to the full status set from the brief;
- add live server actions (`restart`, `health_check`, `maintenance`, `migrate`) into the active control center;
- expand dashboard/traffic/user/server payloads so the UI reflects the new ops model;
- update docs and add regression coverage for the new role restrictions.

## Out of scope
- production deployment;
- runtime credential rotation or secret changes;
- replacing the `dashboard` backend with a different service;
- changing ports, systemd unit names, or nginx assumptions.

## Constraints
- active users must keep working without access loss from panel changes;
- the backend/API seam remains the source of truth for access and operator actions;
- all destructive or sensitive actions must keep audit visibility;
- changes should stay reviewable and reversible.

## Acceptance criteria
- manager-role sessions stay within users/payments/support and cannot read server/settings/finance surfaces they should not own;
- `dashboard/ui` shows working `sync` / `deep repair` actions in the main triage contexts;
- payments support the status set `awaiting payment / awaiting review / confirmed / rejected / expired / disputed / error`;
- servers support `restart / health_check / maintenance / migrate` through the active UI;
- traffic/overview/users/server payloads reflect the control-center status model from the brief;
- docs and tests reflect the completed operator surface.

## Validation
- `./venv/bin/python -m py_compile bot/utils/access.py bot/manual_payments.py dashboard/main.py dashboard/services.py dashboard/v2_data.py`
- `./venv/bin/python -m unittest tests.test_dashboard_api_v2_contract tests.test_dashboard_api_v2_users_contract tests.test_dashboard_api_v2_servers_contract tests.test_dashboard_api_v2_support_contract tests.test_dashboard_api_v2_traffic_contract tests.test_dashboard_api_v2_audit_contract tests.test_dashboard_support_linked_context tests.test_dashboard_legacy_redirects tests.test_dashboard_api_v2_role_access tests.test_dashboard_vpn_repair`
- `dashboard/ui` typecheck
- `git diff --check`
