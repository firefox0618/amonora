# TASK 023 — Repeatable off-host backup (manual script) result

## Status
Completed

## Output

Created:
- `ops/local/backup_core_pg.ps1`
- local runnable copy:
  - `C:\Users\Skyfal\Downloads\backup_core_pg.ps1`

## What it does

- creates a timestamped destination folder on the local machine
- copies core PostgreSQL `.sql.gz` dump files off-host via `scp`
- fails loudly if `scp.exe` or the SSH key are missing
- shows copied files after completion

## What it does not do

- no scheduling
- no cleanup
- no retention management
- no VPN node coverage
- no object-storage upload

## Why this matters

This converts:
- one successful manual backup copy

into:
- one stable operator command that can be rerun safely without improvisation

## Verified run

Validated command:
- `powershell -ExecutionPolicy Bypass -File C:\Users\Skyfal\Downloads\backup_core_pg.ps1`

Validated destination created by the run:
- original proof run:
  - `C:\Users\Skyfal\Downloads\amonora_offhost_backups\core-pg-2026-03-19_19-48`
- current canonical local backup root:
  - `C:\Ops\Backups\amonora`
  - current canonical core PostgreSQL branch:
    - `C:\Ops\Backups\amonora\core-pg`

Validated copied files:
- `amonora_db_.sql.gz`
- `amonora_db_20260316-195700.sql.gz`
