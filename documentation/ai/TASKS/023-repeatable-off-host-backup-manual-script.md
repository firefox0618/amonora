# TASK 023 — Repeatable off-host backup (manual script)

## Status
Completed

## Goal
Turn the first successful one-shot off-host PostgreSQL copy into a repeatable one-command manual operator procedure.

## Scope
- create one local manual script for core PostgreSQL dump copy
- keep it operator-run only
- no cron
- no systemd
- no scheduler
- no VPN node extension yet

## Out of scope
- no server-side script changes
- no automation
- no retention logic
- no S3/object storage rollout
- no VPN-node backup flow

## Implementation

Created script:
- `ops/local/backup_core_pg.ps1`

Behavior:
- creates a timestamped local destination under:
  - `C:\Ops\Backups\amonora\core-pg`
- copies `*.sql.gz` PostgreSQL dump artifacts from:
  - `root@46.21.81.186:/opt/amonora_bot/backups/pg/`
- uses the confirmed Windows SSH key:
  - `C:\Users\Skyfal\.ssh\id_ed25519`
- prints the copied file list after success

## Validation

The script was executed once through Windows PowerShell in manual mode and produced a new off-host copy successfully.

Validated launcher path:
- `C:\Users\Skyfal\Downloads\backup_core_pg.ps1`

Validated command:
- `powershell -ExecutionPolicy Bypass -File C:\Users\Skyfal\Downloads\backup_core_pg.ps1`

## Practical outcome

The workflow is now:
- one command
- repeatable
- still manual
- still low-risk

This is intentionally not yet a backup automation system.
