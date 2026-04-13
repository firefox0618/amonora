# TASK 122 RESULT — Control center shell cutover and redesign

## Result
The old backend-rendered dashboard page shell was retired from active use. Legacy `GET /dashboard/*` page routes now redirect into the root `dashboard/ui` routes, the unused `dashboard/templates/dashboard.html` shell was removed, and the new `Amonora Control` frontend now carries the primary auth/shell/overview experience.

## What changed
- switched legacy dashboard page routes in `dashboard/main.py` from template rendering to redirect behavior into `/overview`, `/users`, `/payments`, `/support`, `/servers`, `/settings`, and `/knowledge`;
- removed the obsolete `dashboard/templates/dashboard.html` template;
- updated dashboard alert deep-links in `dashboard/services.py` to point at the root UI routes;
- redesigned `dashboard/ui` global styling, shared UI primitives, auth pages, app shell, and overview hero around a stronger ash-gray operational direction with richer motion/background treatment;
- added redirect smoke coverage in `tests/test_dashboard_legacy_redirects.py`.

## Validation
- legacy redirect tests pass;
- dashboard API/support/audit contract tests continue to pass;
- `dashboard/ui` typecheck passes;
- diff whitespace check passes.

## Notes
- backend auth/session and API v2 seams remain intact and load-bearing;
- support attachment download routes remain on the backend and were not changed;
- the change is a shell cutover, not a removal of the `dashboard` backend itself.
