# TASK 003 — Dashboard vs dashboard_v2 boundary map

## Status
Completed

## Goal
Clearly define the current responsibility boundary between `dashboard` and `dashboard_v2`.

## Why
The repository currently contains both:
- `dashboard` as an active admin/backend/API layer with legacy UI responsibilities
- `dashboard_v2` as a newer admin UI layer

Without a clear boundary map, feature work and cleanup become risky.

## Context
Relevant docs:
- `documentation/ARCHITECTURE.md`
- `documentation/FEATURES.md`
- `documentation/REPO_RULES.md`
- `documentation/product/DASHBOARD_IMPLEMENTATION_MAP.md`
- `documentation/product/CONTROL_CENTER_VISION.md`
- `documentation/ai/STATE.md`

Relevant code areas:
- `dashboard/`
- `dashboard_v2/`

## Current behavior
Both layers coexist, but the exact split of responsibilities may still be partially unclear.

## Desired behavior
There should be a written boundary map that explains:
- what remains in `dashboard`
- what already exists in `dashboard_v2`
- what is duplicated
- what is legacy-only
- what cannot yet be removed
- what should migrate next

## Scope
- inspect dashboard-related docs and code structure
- identify current page/domain ownership
- identify active backend/API responsibilities in `dashboard`
- identify implemented UI surfaces in `dashboard_v2`
- document migration-sensitive areas

## Out of scope
- moving code
- deleting legacy pages
- refactoring UI
- changing runtime behavior

## Constraints
- do not assume `dashboard` is fully legacy
- do not assume `dashboard_v2` is feature-complete
- preserve current working flows

## Risks
- incorrectly marking active functionality as legacy
- missing hidden dependencies between UI and backend
- planning migration based on incomplete understanding

## Acceptance criteria
- written boundary map exists
- active responsibilities of `dashboard` are listed
- active responsibilities of `dashboard_v2` are listed
- duplicated / transitional areas are identified
- next migration candidates are named

## Validation
Manual review:
- compare docs with repo structure
- verify major admin flows are accounted for
- verify no critical area is silently omitted

## Deliverables
- boundary map document
- short list of “safe next migrations”
- short list of “do not touch yet” areas
