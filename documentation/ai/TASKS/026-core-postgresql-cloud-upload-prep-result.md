# TASK 026 — Core PostgreSQL cloud upload prep result

## Status
Completed

## Output

Prepared:
- `C:\Tools\rclone\rclone.exe`

Updated:
- `ops/local/backup_core_pg.ps1`

## Verified behavior

- local backup still succeeds
- retention still runs
- upload layer is checked safely
- if remote `amonora-backup:` is not configured, upload is skipped without breaking the backup run

## Important note

This is preparation, not confirmed cloud protection yet.

Cloud protection becomes real only after:
- `rclone config`
- remote `amonora-backup:` is created
- at least one successful upload is verified
