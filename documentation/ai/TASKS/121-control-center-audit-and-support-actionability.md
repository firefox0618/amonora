# TASK 121 — Control Center Audit and Support Actionability

## Status
Completed

## Goal
Strengthen the current `dashboard/ui` control center around real operator workflows without replacing the active `dashboard` backend/runtime seam.

## Why
The target control-center spec required two important surfaces that were still weak in the current implementation:
- a dedicated audit view for operator actions;
- ticket-side quick actions that stay linked to the real internal `users.id`, not only the support-ticket identifier.

## Context
Relevant docs and code areas:
- `amonora_control_tz_v4.md`
- `documentation/FEATURES.md`
- `documentation/ai/STATE.md`
- `dashboard/main.py`
- `dashboard/v2_data.py`
- `dashboard/ui/src/components/app-shell.tsx`
- `dashboard/ui/src/app/(dashboard)/support/page.tsx`
- `dashboard/ui/src/app/(dashboard)/audit/page.tsx`

## Current behavior
- audit entries existed in PostgreSQL, but `dashboard/ui` had no dedicated audit screen;
- the topbar did not explicitly show EKB date/time;
- support linked actions were not explicitly bound to the real internal user context for panel-side operations.

## Desired behavior
- operators have a dedicated `Audit log` surface in `dashboard/ui`;
- the topbar shows role and current time/date in `Asia/Yekaterinburg`;
- support detail can safely open the real user record and trigger existing user actions (`Repair VPN`, trial, extend) through the correct internal user ID.

## Scope
- add `/dashboard/api/v2/audit`;
- add `dashboard/ui` audit page and navigation entry;
- add EKB time/role block in the dashboard shell topbar;
- add support linked-user context and safe quick actions in support detail;
- update docs/task bookkeeping.

## Out of scope
- deleting legacy `dashboard`;
- changing payment finalization architecture;
- changing VPN provisioning semantics;
- broad role/permission refactor across the whole panel.

## Constraints
- preserve working user/payment/support flows;
- do not confuse support ticket identifiers with internal `users.id`;
- do not invent fake operational metrics;
- keep changes small, reviewable, and reversible.

## Risks
- wrong ID mapping in support quick actions could target the wrong user;
- audit route/UI changes must not disturb existing v2 contract consumers;
- frontend shell changes must not break navigation or session UX.

## Acceptance criteria
- `dashboard/ui` navigation includes `Audit`;
- `/dashboard/api/v2/audit` returns a stable payload for the new page;
- support detail uses the real linked user context for panel quick actions;
- EKB date/time is visible in the topbar;
- tests and static validation pass.

## Validation
- `python -m unittest tests.test_dashboard_api_v2_audit_contract tests.test_dashboard_support_linked_context tests.test_dashboard_api_v2_support_contract`
- `npm.cmd run typecheck` from the `dashboard/ui` directory via PowerShell
- `python -m compileall dashboard`
- `git diff --check`

## Deliverables
- backend API changes for audit/support context;
- new dashboard audit page;
- support quick actions tied to the correct user context;
- documentation updates in `FEATURES.md` and `STATE.md`
