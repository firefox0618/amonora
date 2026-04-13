# TASK 006 — Backup verification pass

## Status
Completed

## Goal
Verify the real backup mechanisms used in production so future changes can rely on confirmed rollback and recovery paths.

## Why
Runtime inventory confirmed the live production topology, but backup automation, retention, and restore confidence are still not fully mapped.
Before cleanup, migration, deploy-risk changes, or VPN/admin path removal, backup reality must be verified.

## Context
Relevant docs:
- `documentation/RUNBOOK.md`
- `documentation/ops/PRODUCTION_RUNTIME_INVENTORY_2026-03-19.md`
- `documentation/ops/DEPLOY_RULES.md`
- `documentation/ops/ROLLBACK.md`
- `documentation/vpn/VPN_CONFIG_STRATEGY.md`
- `documentation/ai/STATE.md`

Relevant runtime areas:
- PostgreSQL on core server
- `/opt/3x-ui/backups` on VPN nodes
- cron/systemd timers
- dump scripts
- backup directories
- any off-server backup destination if present

## Current behavior
Some backup locations are known, but the actual automation, retention, and restore-readiness are not yet fully confirmed from live runtime.

## Desired behavior
There should be a verified backup document that confirms:
- what is backed up
- where backups are stored
- how backups are triggered
- how often they run
- what retention exists
- which backups are local-only
- whether there is evidence of successful recent backups
- what restore path is expected
- what still requires verification

## Scope
- inspect backup-related directories
- inspect cron jobs, timers, and scripts related to dumps/backups
- inspect PostgreSQL dump presence/paths if applicable
- inspect 3x-ui backup locations on VPN nodes
- identify naming conventions and timestamp patterns
- identify evidence of recent successful backup artifacts
- identify whether backups are local-only or copied elsewhere
- record unresolved restore-confidence gaps

## Out of scope
- creating new backups
- editing backup scripts
- deleting old backups
- rotating retention manually
- restoring from backups
- changing production config

## Constraints
- read-only only
- do not expose secrets in tracked docs
- do not assume presence of files means restorable backups without evidence
- clearly separate confirmed facts from inferred assumptions

## Risks
- backup files exist but are stale
- backup scripts exist but are not active
- retention may be undefined
- restore process may be undocumented or incomplete
- local-only backups may not protect against full host loss

## Acceptance criteria
- backup verification document exists
- database backup situation is described
- VPN/3x-ui backup situation is described
- automation source (cron/systemd/script/manual) is described where known
- retention/rotation is described where known
- unresolved restore risks are explicitly listed

## Validation
Manual checks:
- verify backup directories on live servers
- verify timers/cron entries related to backup jobs
- verify recent backup artifact timestamps
- verify whether backup destinations are local-only or copied elsewhere
- verify no secrets are added to tracked docs

## Deliverables
- backup verification document
- updates for `RUNBOOK.md` if needed
- explicit list of backup-confidence gaps
- follow-up restore/readiness tasks
