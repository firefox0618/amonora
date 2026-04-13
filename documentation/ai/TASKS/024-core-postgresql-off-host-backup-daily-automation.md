# TASK 024 — Core PostgreSQL off-host backup daily automation

## Status
Completed

## Goal
Convert the repeatable manual core PostgreSQL off-host backup command into a narrow once-per-day local automation.

## Scope
- local machine only
- core PostgreSQL dump copy only
- daily schedule
- reuse the already validated manual backup script

## Out of scope
- no server-side changes
- no cron/systemd changes on production
- no VPN node automation
- no retention automation
- no object storage rollout
- no backup pipeline redesign

## Implementation

Created:
- `ops/local/register_core_pg_backup_task.ps1`

The automation model is intentionally narrow:
- Windows Task Scheduler
- one daily run
- script path copied to a stable local Windows directory
- reuses:
  - `backup_core_pg.ps1`

## Schedule

Configured schedule:
- daily at `09:00`

## Important operating note

The scheduled task is registered with interactive user logon semantics.
This keeps the first automation simple and low-risk, but it is not yet the final production-grade backup governance model.
