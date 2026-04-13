# TASK 025 — Core PostgreSQL off-host backup retention result

## Status
Completed

## What changed

Updated:
- `ops/local/backup_core_pg.ps1`

Added behavior:
- after successful copy, the script scans local folders matching `core-pg-*`
- folders older than `7` days are removed automatically

## Why this is safe

- retention runs only on the local machine
- retention is limited to the dedicated core PostgreSQL off-host backup folder pattern
- canonical local backup root is now:
  - `C:\Ops\Backups\amonora`
  - PostgreSQL backup branch:
    - `C:\Ops\Backups\amonora\core-pg`
- no production host files are modified

## Practical outcome

The local backup flow now has:
- manual copy proof
- repeatable operator script
- daily automation
- basic retention cleanup
