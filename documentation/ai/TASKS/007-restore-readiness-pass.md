# TASK 007 — Restore-readiness pass

## Status
Completed

## Goal
Assess restore readiness from currently confirmed backup artifacts and recovery scripts without performing a live restore.

## Why
Backup artifacts are confirmed to exist for PostgreSQL and `3x-ui`, and database restore scripts are present on the core host.
However, actual restore confidence is still incomplete.
Before risky cleanup, migrations, or operational changes, restore-readiness must be evaluated explicitly.

## Context
Relevant docs:
- `documentation/RUNBOOK.md`
- `documentation/ops/PRODUCTION_RUNTIME_INVENTORY_2026-03-19.md`
- `documentation/ops/BACKUP_VERIFICATION_2026-03-19.md`
- `documentation/ops/DEPLOY_RULES.md`
- `documentation/ops/ROLLBACK.md`
- `documentation/ai/STATE.md`

Relevant runtime areas:
- PostgreSQL dumps on core host
- restore scripts on core host
- `3x-ui` backup artifacts on VPN nodes
- any documented/manual rollback notes

## Current behavior
Backup artifacts and some restore-related scripts exist, but no fully verified restore readiness model is yet documented.

## Desired behavior
There should be a restore-readiness document that explains:
- what can currently be restored
- from which artifacts
- by which scripts or manual flows
- in what order
- with what gaps or risks
- what is still not restorable with confidence

## Scope
- inspect restore-related scripts in read-only mode
- inspect naming and expected inputs of backup artifacts
- map expected restore order for:
  - PostgreSQL
  - `3x-ui` DB/config
  - key app/runtime materials if relevant
- identify missing prerequisites, undocumented steps, and hidden assumptions
- record restore-confidence gaps

## Out of scope
- performing a restore
- editing restore scripts
- changing production config
- generating fresh backups
- deleting old artifacts

## Constraints
- read-only only
- do not expose secrets in tracked docs
- do not present script presence as proof of successful restore
- clearly separate confirmed restore mechanics from inferred assumptions

## Risks
- restore scripts may depend on undocumented paths or credentials
- backup format may not match script expectations
- restore may be possible only partially
- app/runtime config may be less recoverable than DB artifacts

## Acceptance criteria
- restore-readiness document exists
- PostgreSQL restore path is described at a high level
- `3x-ui` restore path is described at a high level
- missing steps and confidence gaps are explicitly listed
- no secrets are committed into tracked docs

## Validation
Manual checks:
- inspect restore script filenames, arguments, and referenced paths
- compare scripts to actual backup artifact names/locations
- identify whether restore order is coherent
- verify tracked docs do not contain sensitive values

## Deliverables
- restore-readiness document
- updates for `RUNBOOK.md` if needed
- explicit restore-confidence gaps
- follow-up tasks for hardening restore governance
