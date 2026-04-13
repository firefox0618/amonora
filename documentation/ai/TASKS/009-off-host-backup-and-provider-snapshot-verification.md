# TASK 009 — Off-host backup and provider snapshot verification

## Status
Completed

## Goal
Verify whether production backup protection extends beyond local host storage by confirming any off-host backup replication, provider snapshots, or external recovery mechanisms.

## Why
Current backup governance confirms real local backup artifacts, but off-host protection is not yet proven.
Without off-host backup or reliable provider-level recovery, local backup presence does not protect against total host loss.

## Context
Relevant docs:
- `documentation/RUNBOOK.md`
- `documentation/ops/PRODUCTION_RUNTIME_INVENTORY_2026-03-19.md`
- `documentation/ops/BACKUP_VERIFICATION_2026-03-19.md`
- `documentation/ops/RESTORE_READINESS_2026-03-19.md`
- `documentation/ops/BACKUP_GOVERNANCE_AND_RETENTION_MAP_2026-03-19.md`
- `documentation/ops/DEPLOY_RULES.md`
- `documentation/ops/ROLLBACK.md`
- `documentation/ai/STATE.md`

Relevant areas:
- provider panels for core and VPN nodes
- any snapshot/backup settings at VPS provider level
- any off-host replication scripts or destinations
- any object storage / external disk / remote rsync / SCP / rclone destinations
- any documented or undocumented disaster-recovery assumptions

## Current behavior
Local backup artifacts are confirmed.
Off-host backup protection and provider snapshot coverage are not yet confirmed.

## Desired behavior
There should be a verified document that explains:
- whether provider snapshots exist
- whether snapshots are scheduled or manual
- whether any off-host backup copy exists
- which hosts are covered
- which asset classes are protected off-host
- which assumptions are still unproven
- what the current host-loss protection posture actually is

## Scope
- inspect provider-side backup/snapshot features for each production host
- inspect server-side evidence of off-host replication if any
- inspect scripts/configs for rsync/scp/rclone/s3-style backup copies if any
- classify each host as:
  - local-only backups
  - provider snapshots confirmed
  - external replication confirmed
  - unknown
- identify host-loss recovery gaps

## Out of scope
- enabling provider snapshots
- purchasing storage
- configuring replication
- changing backup scripts
- restoring from snapshots
- modifying production services

## Constraints
- read-only only
- do not expose secrets in tracked docs
- do not assume provider snapshot existence without confirmation
- clearly separate confirmed protection from inferred assumptions

## Risks
- provider snapshots may exist but not be scheduled
- snapshots may cover disks but not guarantee application consistency
- off-host replication may be partial or stale
- operator assumptions may overestimate recovery posture

## Acceptance criteria
- verification document exists
- each production host has an off-host protection status
- provider snapshot status is described where known
- external replication status is described where known
- host-loss protection gaps are explicitly listed
- no secrets are committed into tracked docs

## Validation
Manual checks:
- verify provider panel evidence for each host
- verify any off-host replication script or destination if present
- verify tracked docs contain no sensitive values
- verify unknowns remain marked as unknown, not assumed

## Deliverables
- off-host protection verification document
- host-by-host protection status
- explicit host-loss recovery gaps
- follow-up hardening tasks
