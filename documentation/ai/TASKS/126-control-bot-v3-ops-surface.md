## Task 126

### Title
Control Bot v3 operational surface

### Context
`@amonora_control_bot` already existed as an internal alerts/review bot, but the v3 control-bot spec required it to become a real Telegram operational console for the live production team.

The missing gaps were:

- new IA around `Dashboard / Problems / Support / Notifications`;
- quick-open and actionability for users, support tickets, nodes, and login-code flows;
- better alignment with panel roles and panel-side backend seams;
- more truthful auth/session visibility and 5-minute login codes;
- support-aware notification buckets and support-related control events.

### Scope

- expand `control_bot` screens and callbacks without removing old aliases;
- wire control-bot actions into the same `dashboard.services` and support storage seams used by the panel;
- keep live payment review stable;
- keep owner-only broadcast/trigger layer intact;
- add or update focused tests and state/docs.

### Constraints

- no breaking rewrite of `control_bot`;
- no duplicate business logic that diverges from `dashboard` and `support_bot`;
- changes must stay safe for active production users and current admins.

### Acceptance criteria

- `@amonora_control_bot` exposes `dashboard`, `problems`, `support`, `notifications`, `user` flows;
- admin can open a user card and run `sync / deep repair / trial / extend / block / clear-access`;
- admin can open a support ticket and `assign / reply / transfer / close`;
- admin can open a node and run `health check / restart / maintenance / resync(refresh)`;
- panel login-code delivery uses 5-minute TTL and the bot shows masked recent auth codes plus active sessions;
- notification preferences include `support` and `security` buckets with role-aware defaults;
- support activity creates safe control events without turning support traffic into a hard dependency on control-event delivery.

### Validation

- `python -m py_compile` for touched python modules;
- focused `unittest` suite for control-bot queries/router/dispatcher plus payment/support/dashboard auth seams.
