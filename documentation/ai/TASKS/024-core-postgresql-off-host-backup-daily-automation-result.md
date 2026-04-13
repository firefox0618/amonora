# TASK 024 — Core PostgreSQL off-host backup daily automation result

## Status
Completed

## Output

Created:
- `ops/local/register_core_pg_backup_task.ps1`

Registered local automation:
- task name:
  - `Amonora Core PG Backup Daily`
- schedule:
  - daily at `09:00`
- task state after registration:
  - `Ready`
- next run time:
  - `2026-03-20 09:00`

Stable local script path:
- `C:\Users\Skyfal\Scripts\amonora\backup_core_pg.ps1`

Current local backup target:
- `C:\Ops\Backups\amonora\core-pg`

## Practical outcome

The core PostgreSQL off-host backup flow now has three layers:

1. one-shot manual copy proven
2. repeatable manual script proven
3. first local daily automation enabled

## Scheduler verification

Verified through Windows Task Scheduler / PowerShell:
- action executable:
  - `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`
- action arguments:
  - `-NoProfile -ExecutionPolicy Bypass -File "C:\Users\Skyfal\Scripts\amonora\backup_core_pg.ps1"`
- trigger:
  - daily
  - start boundary `2026-03-19T09:00:00+05:00`

## Still intentionally not covered

- VPN node backups
- off-host object storage
- retention policy
- failure alerting
- centralized backup governance
