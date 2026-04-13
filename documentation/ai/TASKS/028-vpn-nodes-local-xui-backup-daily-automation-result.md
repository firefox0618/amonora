# TASK 028 — VPN nodes local XUI backup daily automation result

## Status
Completed

## Output

Created:
- `ops/local/register_vpn_xui_backup_task.ps1`

Registered local automation:
- task name:
  - `Amonora VPN XUI Backup Daily`
- schedule:
  - daily at `09:15`
- task state after registration:
  - `Ready`
- next run time:
  - `2026-03-20 09:15`

Stable local script path:
- `C:\Users\Skyfal\Scripts\amonora\backup_vpn_xui_artifacts.ps1`

## Scheduler verification

Verified through Windows Task Scheduler / PowerShell:
- action executable:
  - `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`
- action arguments:
  - `-NoProfile -ExecutionPolicy Bypass -File "C:\Users\Skyfal\Scripts\amonora\backup_vpn_xui_artifacts.ps1"`
- trigger:
  - daily
  - start boundary `2026-03-19T09:15:00+05:00`
