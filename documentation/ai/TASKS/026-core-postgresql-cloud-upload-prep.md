# TASK 026 — Core PostgreSQL cloud upload prep

## Status
Completed

## Goal
Prepare the core PostgreSQL off-host backup flow for optional cloud upload through `rclone`, without forcing cloud upload before a remote is configured.

## Scope
- local machine only
- prepare stable `rclone` path
- add optional upload step to the existing backup script
- skip safely when the remote is not configured yet

## Out of scope
- no server-side changes
- no object-storage provider selection finalization inside the script
- no forced upload before remote configuration exists
- no VPN-node extension yet

## Implementation

Created stable local binary path:
- `C:\Tools\rclone\rclone.exe`

Updated:
- `ops/local/backup_core_pg.ps1`

Behavior now:
- performs local backup copy
- performs local retention cleanup
- checks whether `rclone` exists
- checks whether remote `amonora-backup:` exists
- uploads only if both are true
- otherwise prints a safe skip message

## Practical result

The backup flow is now ready for cloud upload activation, but it does not pretend cloud protection exists until the `rclone` remote is actually configured.
