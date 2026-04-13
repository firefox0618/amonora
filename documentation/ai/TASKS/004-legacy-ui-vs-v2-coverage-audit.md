# TASK 004 — Legacy UI vs dashboard_v2 coverage audit

## Status
Completed

## Goal
Determine which legacy `dashboard` UI flows are already covered by `dashboard_v2`, which are partially covered, and which still exist only in legacy UI.

## Why
The boundary map confirmed that:
- `dashboard` is still critical as backend/API/auth/service layer
- `dashboard_v2` is the main new UI
- duplication is mostly at the UI/route layer
- Jinja UI is legacy, but not yet safe to remove

The next safe step is to measure actual UI coverage before any cleanup or migration decisions.

## Context
Relevant docs:
- `documentation/product/DASHBOARD_BOUNDARY_MAP.md`
- `documentation/ARCHITECTURE.md`
- `documentation/FEATURES.md`
- `documentation/REPO_RULES.md`
- `documentation/product/DASHBOARD_IMPLEMENTATION_MAP.md`
- `documentation/ai/STATE.md`

Relevant code areas:
- `dashboard/`
- `dashboard_v2/`

## Current behavior
Legacy UI and new UI coexist. Some flows may already be migrated, some may be partial, and some may still depend only on legacy UI.

## Desired behavior
There should be a clear coverage matrix showing:
- legacy-only flows
- v2-only flows
- duplicated flows
- partial migrations
- unknown/unverified areas

## Scope
- inventory major admin/user-facing dashboard flows
- compare legacy UI routes/pages with dashboard_v2 pages
- identify which flows depend on legacy templates
- identify missing UI coverage in v2
- identify flows safe for future migration planning

## Out of scope
- deleting legacy UI
- moving routes
- changing backend behavior
- redesigning pages
- runtime cleanup

## Constraints
- do not assume route name similarity means feature equivalence
- do not mark a flow as migrated without verifying practical coverage
- preserve distinction between UI coverage and backend/API ownership

## Risks
- false assumption that a v2 screen fully replaces a legacy flow
- hidden admin actions existing only in legacy templates
- incomplete mapping of settings/support/payment edge cases

## Acceptance criteria
- coverage audit document exists
- major dashboard flows are listed
- each flow is marked as one of:
  - legacy only
  - v2 only
  - both
  - partial
  - unknown
- high-risk legacy-only flows are identified
- next safe migration candidates are identified

## Validation
Manual review:
- compare route inventory with actual page/function coverage
- verify critical admin flows are included
- verify edge-case flows are not silently skipped

## Deliverables
- coverage audit document
- migration candidate list
- do-not-remove-yet list
