# TASK 029 — Restore drill result

## Status
Completed

## Scope

This restore drill was performed locally only.

No production server was modified.
No live restore was attempted on production.

## PostgreSQL backup checked

Checked file:
- `C:\Ops\Backups\amonora\core-pg\2026-03-19_20-29\amonora_db_20260316-195700.sql.gz`

Local drill actions:
- gzip integrity had already passed during earlier backup verification
- local copy was unpacked successfully
- unpacked SQL file was inspected
- schema/data markers were verified

Observed result:
- unpacked file size:
  - `33K`
- unpacked line count:
  - `886`
- file header is a valid PostgreSQL dump text export
- `CREATE TABLE` statements are present
- `COPY ... FROM stdin` data sections are present
- dump has a valid completion footer:
  - `PostgreSQL database dump complete`
- `COPY` sections include `\.` terminators

Examples confirmed:
- `dashboard_admins`
- `dashboard_audit_logs`
- `dashboard_sessions`
- `managed_servers`
- `payment_records`
- `support_tickets`
- `users`
- `vpn_clients`

PostgreSQL conclusion:
- restore possible: `partial-confirmed`
- meaning:
  - backup is readable
  - schema is present
  - data payload is present
  - dump looks structurally complete rather than truncated
- limitation:
  - no full import into a local PostgreSQL instance was performed in this drill
  - local environment currently has no `psql`, `createdb`, `postgres`, or `docker`
  - local `psql` restore therefore remains unverified until a temporary local PostgreSQL runtime is available

## VPN XUI backup checked

Checked files:
- `C:\Ops\Backups\amonora\vpn-de\2026-03-19_20-29\x-ui.db`
- `C:\Ops\Backups\amonora\vpn-ee\2026-03-19_20-29\x-ui.db`

Local drill actions:
- verified SQLite file header
- opened both files with Python `sqlite3`
- queried `sqlite_master`
- listed tables

Observed result:
- both files identify as `SQLite format 3`
- both files open successfully
- both files expose tables

Tables confirmed on both node DBs:
- `client_traffics`
- `history_of_seeders`
- `inbound_client_ips`
- `inbounds`
- `outbound_traffics`
- `settings`
- `sqlite_sequence`
- `users`

VPN conclusion:
- restore possible: `partial-confirmed`
- meaning:
  - DB files are structurally valid SQLite databases
  - core table structure is present
- limitation:
  - no live `3x-ui` service-side restore was attempted

## Overall result

Overall drill result:
- `restore possible / partial`

What is now confirmed:
- PostgreSQL dump is not just a dead archive; it expands into plausible restore material
- Germany and Estonia `x-ui.db` artifacts are real readable SQLite databases with expected tables

What is still not confirmed:
- full PostgreSQL import into a local test cluster
- full `3x-ui` application restore from these DB files
- end-to-end application recovery sequence

## Practical meaning

This is a meaningful improvement over "backup exists, maybe usable".

Current confidence is now:
- PostgreSQL artifact validity: medium
- `x-ui.db` artifact validity: medium
- full restore readiness: still partial
