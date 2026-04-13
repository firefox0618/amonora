# TASK 027 — VPN nodes local x-ui backup result

## Status
Completed

## Output

Created:
- `ops/local/backup_vpn_xui_artifacts.ps1`

## Sources copied

Germany node:
- `root@213.108.20.34:/opt/3x-ui/db/x-ui.db`
- `root@213.108.20.34:/opt/3x-ui/backups/*`

Estonia node:
- `root@185.88.37.71:/opt/3x-ui/db/x-ui.db`
- `root@185.88.37.71:/opt/3x-ui/backups/*`

## Local destination pattern

- `C:\Ops\Backups\amonora\vpn-de\<timestamp>`
- `C:\Ops\Backups\amonora\vpn-ee\<timestamp>`

## Verified run

Validated destination folders:
- `C:\Ops\Backups\amonora\vpn-de\2026-03-19_20-29`
- `C:\Ops\Backups\amonora\vpn-ee\2026-03-19_20-29`

Validated copied artifacts:

Germany:
- `x-ui.db`
- `x-ui.db.20260316-205700`

Estonia:
- `x-ui.db`
- `x-ui.db.20260316-195700`
- `x-ui.db.20260317-220759`
- `config.json.20260317-220759`

## Practical outcome

The backup posture is now stronger on the local machine:
- core PostgreSQL off-host copy exists
- Germany `3x-ui` node artifacts now also have local off-host copy
- Estonia `3x-ui` node artifacts now also have local off-host copy
