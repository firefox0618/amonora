# TASK 123 RESULT — Control center ops completion

## Result
The active `dashboard/ui` control center now covers the remaining operator flows from the final brief without returning to the old shell. Role boundaries are enforced at the backend read/action layer, user triage now has `sync` and `deep repair` in every important context, payment statuses cover the full manual-review flow, and servers expose live node actions from the main UI.

## What changed
- added resilient user-status/access helpers and expanded payment labels for `disputed` and `error`;
- implemented role-aware permission helpers and enforced them across v2 read endpoints, finance endpoints, and session navigation;
- expanded v2 payloads for users, payments, servers, traffic, overview, and linked support/payment user contexts;
- wired `sync` / `deep repair` endpoints and UI actions into users, support, payments, and overview;
- added server actions `restart`, `health_check`, `maintenance`, and regional migration to the active server screen;
- limited finance visibility/actions inside `payments` for roles that should not own finance;
- added a role-access smoke test so manager-role sessions cannot drift back into server/settings/finance read surfaces.

## Validation
- Python compile checks pass;
- `33` dashboard contract/repair/role tests pass;
- frontend typecheck passes;
- diff whitespace check passes.

## Notes
- the implementation keeps the `dashboard` backend as the load-bearing auth/API seam;
- no deployment was performed as part of this task;
- active-user safety was preserved by layering the new behavior onto the existing access/payment/support flows instead of replacing them wholesale.
