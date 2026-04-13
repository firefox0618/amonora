# TASK 008 — Backup governance and retention map

## Status
Completed

## Goal
Map the real backup governance model: what is backed up, how it is triggered, where it is stored, how long it is retained, and where the current process still depends on manual operator knowledge.

## Why
Backup artifacts and partial restore paths are confirmed, but backup governance is still incomplete.
Before cleanup, migrations, or more confident production changes, the project needs a clear operational model of backup ownership, schedule, retention, and recovery assumptions.

## Context
Relevant docs:
- `documentation/RUNBOOK.md`
- `documentation/ops/PRODUCTION_RUNTIME_INVENTORY_2026-03-19.md`
- `documentation/ops/BACKUP_VERIFICATION_2026-03-19.md`
- `documentation/ops/RESTORE_READINESS_2026-03-19.md`
- `documentation/ops/DEPLOY_RULES.md`
- `documentation/ops/ROLLBACK.md`
- `documentation/ai/STATE.md`

Relevant runtime areas:
- PostgreSQL backup artifacts on core host
- backup directories on VPN nodes
- restore scripts on core host
- cron/systemd/manual backup triggers
- any local/off-host backup destinations
- retention/rotation evidence

## Current behavior
Backup artifacts exist, and partial restore paths exist, but governance is not yet clearly documented.
Some backup and restore logic appears to depend on historical scripts, manual actions, and implicit operational knowledge.

## Desired behavior
There should be a governance map that explains:
- what data/config classes are protected
- where each class is backed up
- how backup is triggered
- whether it is manual, scripted, timer-based, panel-driven, or unknown
- how long artifacts are retained
- whether artifacts are local-only or replicated elsewhere
- who/what the restore path depends on
- which parts are still fragile

## Scope
- classify current backups by asset type:
  - PostgreSQL
  - 3x-ui DB/config
  - app/runtime config
  - nginx/systemd/env snapshots if present
  - JSON/tarball operational artifacts
- map trigger type:
  - manual
  - script
  - cron
  - systemd timer
  - app/panel-internal
  - unknown
- map storage class:
  - local only
  - copied elsewhere
  - unknown
- map retention evidence:
  - visible timestamp range
  - overwrite behavior
  - rotation evidence
  - unknown
- identify governance gaps and operator-memory dependencies

## Out of scope
- changing backup scripts
- configuring retention
- adding new storage
- deleting old artifacts
- performing restore
- changing production services

## Constraints
- read-only only
- do not expose secrets in tracked docs
- do not invent retention rules if they are not actually proven
- clearly distinguish confirmed facts from inference

## Risks
- backup artifacts may exist without clear ownership
- retention may be accidental rather than designed
- restore assumptions may live only in scripts or operator memory
- local-only backups may create false confidence

## Acceptance criteria
- backup governance document exists
- each major asset class has an identified backup posture
- trigger type is mapped where known
- storage class is mapped where known
- retention/rotation is mapped where known
- governance gaps are explicitly listed
- operator-memory dependencies are explicitly listed

## Validation
Manual checks:
- compare artifact evidence with scripts/timers/cron where available
- verify whether retention is observable or only assumed
- verify whether any off-host copy is actually confirmed
- verify no secrets are committed into tracked docs

## Deliverables
- backup governance document
- retention/rotation map
- operator-memory risk list
- follow-up hardening tasks
