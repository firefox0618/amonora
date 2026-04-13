# TASK 028 — VPN nodes local XUI backup daily automation

## Status
Completed

## Goal
Add a daily local automation for `backup_vpn_xui_artifacts.ps1` so Germany and Estonia node artifacts are copied off-host to the PC on a regular schedule.

## Why
The local backup layer is now working and verified for:
- core PostgreSQL
- Germany VPN node artifacts
- Estonia VPN node artifacts

The next safe step is to make the VPN backup path repeatable on a schedule, just like core PostgreSQL, without changing anything on production servers.

## Context
Relevant docs:
- `documentation/ops/OFF_HOST_BACKUP_PLAN.md`
- `documentation/archive/snapshots/STAGE_CHECKPOINT_2026-03-19.md`
- `documentation/ai/STATE.md`

Relevant local scripts:
- `ops/local/backup_vpn_xui_artifacts.ps1`
- existing scheduled core task:
  - `Amonora Core PG Backup Daily`

Relevant local paths:
- `C:\Ops\Backups\amonora\vpn-de\`
- `C:\Ops\Backups\amonora\vpn-ee\`
- stable runnable scripts location:
  - `C:\Users\Skyfal\Scripts\amonora\`

## Current behavior
VPN node backups can be copied locally and verified manually, but there is no daily scheduled automation for them yet.

## Desired behavior
A Windows Scheduled Task should run `backup_vpn_xui_artifacts.ps1` automatically every day, using the stable script path on the local machine.

## Scope
- create a local PowerShell registration script for the VPN backup task
- register one daily Windows Scheduled Task
- point it to the stable local script copy
- verify:
  - task exists
  - task state is `Ready`
  - next run time is set
  - action path is correct

## Out of scope
- no server changes
- no cron/systemd changes on production
- no retention redesign
- no object storage upload
- no merging core and VPN tasks into one scheduler unit
- no changes to backup payload contents

## Constraints
- keep the automation local-only
- keep the task independent from production hosts
- prefer the same style and conventions as the core PostgreSQL scheduled task
- do not widen scope into monitoring/alerts yet

## Risks
- wrong script path in the scheduled task
- task created under the wrong working assumptions
- quoting/path issues in Windows task action
- false confidence if registration succeeds but script path is stale

## Acceptance criteria
- a registration script exists
- a Windows scheduled task for VPN backup is registered
- task state is `Ready`
- next run time is visible
- action points to the stable local script path
- no production systems are modified

## Validation
Manual checks:
- verify task name
- verify action command
- verify trigger schedule
- verify stable script path exists
- optionally run the task manually once after registration

## Deliverables
- local registration script
- registered Windows scheduled task
- short result note with:
  - task name
  - schedule
  - action path
  - status
