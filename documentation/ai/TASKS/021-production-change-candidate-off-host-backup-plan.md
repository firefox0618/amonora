# TASK 021 — Production change candidate: off-host backup plan

## Status
Completed

## Goal
Design a safe, minimal, and realistic off-host backup strategy for production without applying any changes yet.

## Why
Current state:
- backups exist locally on servers
- restore path is partial and fragile
- no off-host backup confirmed
- no provider snapshots enabled

This means:
- total host loss = high-risk scenario
- current system is not safe for aggressive changes or migrations

Before any real production changes, backup safety must be improved.

## Context
Relevant docs:
- `documentation/ops/PRODUCTION_RUNTIME_INVENTORY_2026-03-19.md`
- `documentation/ops/BACKUP_VERIFICATION_2026-03-19.md`
- `documentation/ops/RESTORE_READINESS_2026-03-19.md`
- `documentation/ops/BACKUP_GOVERNANCE_AND_RETENTION_MAP_2026-03-19.md`
- `documentation/ops/OFF_HOST_BACKUP_AND_PROVIDER_SNAPSHOT_VERIFICATION_2026-03-19.md`
- `documentation/ops/BASELINE_DIFF_AUDIT_2026-03-19.md`
- `documentation/ai/STATE.md`

Infrastructure:
- core: `46.21.81.186`
- vpn nodes:
  - `213.108.20.34` (DE)
  - `185.88.37.71` (EE)

## Scope
- analyze possible off-host backup strategies
- define minimal viable solution
- define rollout steps (no execution)
- define rollback and failure scenarios

## Out of scope
- enabling backups
- modifying servers
- installing tools
- changing cron/systemd
- uploading data to external storage

## Candidate approaches

### Option A — Provider snapshots
- enable VPS snapshots (if available)
- pros:
  - simplest
  - full-machine coverage
- cons:
  - cost
  - provider lock-in
  - unclear retention guarantees

### Option B — External object storage (S3 / compatible)
- push:
  - PostgreSQL dumps
  - `3x-ui` backups
- tools:
  - `rclone` / `restic` / custom script
- pros:
  - portable
  - flexible retention
- cons:
  - requires setup
  - credentials management

### Option C — Remote backup host (`rsync` / `scp`)
- push backups to another VPS
- pros:
  - simple
  - full control
- cons:
  - still single-provider risk
  - needs maintenance

## Required coverage
Define explicitly what must be protected:

- PostgreSQL:
  - `amonora_db` dumps

- Application data:
  - `/opt/amonora_bot/backups/*`
  - support/payment artifacts

- VPN nodes:
  - `/opt/3x-ui/db/x-ui.db`
  - `/opt/3x-ui/backups/*`

- Optional:
  - `nginx` configs
  - env snapshots (without secrets in repo)

## Deliverables

1. Selected approach (`A` / `B` / `C` or hybrid)
2. Minimal rollout plan:
   - steps
   - order
   - what to verify after each step
3. Backup scope definition:
   - what is included
   - what is not
4. Retention model:
   - how many copies
   - how often
5. Failure scenarios:
   - backup fails
   - storage unavailable
   - partial backup
6. Restore assumptions:
   - what this plan guarantees
   - what it does not guarantee

## Acceptance criteria
- clear chosen strategy
- explicit list of protected data
- explicit rollout plan (step-by-step)
- explicit risks and limitations
- no production changes performed

## Validation
Manual checks:
- plan is executable by one operator
- no hidden dependencies
- no reliance on undocumented knowledge
- consistent with current runtime topology

## Output file
- `documentation/ops/OFF_HOST_BACKUP_PLAN.md`
