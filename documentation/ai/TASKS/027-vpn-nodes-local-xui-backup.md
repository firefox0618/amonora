# TASK 027 — VPN nodes local x-ui backup

## Status
Completed

## Goal
Extend the local off-host backup pattern to the Germany and Estonia VPN nodes by copying `3x-ui` live DB and backup artifacts to the local machine.

## Scope
- local machine only
- Germany node:
  - `213.108.20.34`
- Estonia node:
  - `185.88.37.71`
- assets:
  - `/opt/3x-ui/db/x-ui.db`
  - `/opt/3x-ui/backups/*`

## Out of scope
- no server-side changes
- no scheduler yet for VPN backups
- no cloud upload
- no retention beyond local 7-day cleanup
- no restore automation

## Implementation

Created:
- `ops/local/backup_vpn_xui_artifacts.ps1`

Behavior:
- creates timestamped local folders under:
  - `C:\Ops\Backups\amonora\vpn-de`
  - `C:\Ops\Backups\amonora\vpn-ee`
- copies live `x-ui.db` and `/opt/3x-ui/backups/*` from both VPN nodes
- applies local 7-day retention for:
  - `vpn-de\*`
  - `vpn-ee\*`

## Validation

The script was executed once successfully after creation.
