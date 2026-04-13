# TASK 025 — Core PostgreSQL off-host backup retention

## Status
Completed

## Goal
Add minimal retention cleanup for locally stored off-host core PostgreSQL backup folders so daily automation does not grow without bounds.

## Scope
- local machine only
- only folders matching:
  - `core-pg-*`
- keep rolling local retention by age
- no production-server changes

## Out of scope
- no changes on core host
- no VPN node retention
- no cloud/object-storage retention
- no server-side cleanup
- no backup format change

## Implementation

Retention was added to:
- `ops/local/backup_core_pg.ps1`

Rule:
- keep local `core-pg-*` backup folders from the last `7` days
- remove matching folders older than `7` days

## Safety boundary

Retention targets only:
- `C:\Ops\Backups\amonora\core-pg\*`

It does not touch:
- server-side backups
- non-core backup folders
- unrelated Windows directories
