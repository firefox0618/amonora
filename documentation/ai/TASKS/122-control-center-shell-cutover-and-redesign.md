# TASK 122 — Control center shell cutover and redesign

## Status
Completed

## Goal
Retire the old backend-rendered dashboard page shell from active use and make the new `dashboard/ui` control center the explicit primary operator surface, with a stronger visual shell and operational-first overview.

## Why
- the new admin UI already existed as the main Next.js surface, but legacy backend-rendered page routes and the old `dashboard.html` shell still remained in the repository;
- the current control-center brief requires a more deliberate operational interface, not a partial migration with historical UI still lingering as a first-class shell;
- the change must preserve active production flows and keep the backend/API layer intact for users, admins, support, and payment actions.

## Scope
- convert legacy `GET /dashboard/*` page routes into redirects into the new root admin UI;
- remove the unused legacy `dashboard.html` template shell;
- redesign the `dashboard/ui` shell, auth entrypoints, and overview top section around a stronger `Amonora Control` visual direction;
- keep existing API v2 contracts and action endpoints stable;
- update task/docs state to reflect the cutover.

## Out of scope
- changing payment/access/support domain logic;
- removing backend auth/session logic;
- removing support attachment routes;
- changing public landing routing;
- changing production ports or service names.

## Constraints
- no breakage for active users or current bot flows;
- `dashboard` backend must stay operational as auth/API/service seam;
- legacy page routes may stop rendering HTML, but deep operational actions must keep working through API v2 and the new UI;
- keep changes reversible and validate with tests/typecheck.

## Acceptance criteria
- legacy dashboard page routes no longer render the old shell;
- the old `dashboard.html` template is removed from active code;
- `dashboard/ui` presents a stronger primary shell with updated auth, nav, topbar, and overview hero;
- internal links and alerts point to the new UI routes instead of legacy page URLs where relevant;
- tests cover the redirect behavior and existing API surfaces still validate cleanly.

## Validation
- `python -m unittest tests.test_dashboard_legacy_redirects ...`
- `dashboard/ui` typecheck
- `git diff --check`
