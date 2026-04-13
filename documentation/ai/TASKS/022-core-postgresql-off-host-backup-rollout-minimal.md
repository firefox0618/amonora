# TASK 022 — Core PostgreSQL off-host backup rollout (minimal)

## Status
Completed

## Goal
Perform the first real production change by introducing a minimal off-host backup for PostgreSQL dumps on the core host.

## Scope
- host: core only (`46.21.81.186`)
- asset: existing PostgreSQL dump files only
- mode: one-shot manual upload
- no automation yet

## Out of scope
- no changes to existing backup scripts
- no cron/systemd changes
- no VPN node backups
- no retention automation
- no config/env backup
- no refactor

## Preconditions
Confirmed before execution:

1. SSH access worked to the core host
2. latest dump locations were readable:
   - `/opt/amonora_bot/backups/`
   - `/opt/amonora_bot/backups/pg/`
3. selected dump existed and was non-empty

## Selected artifact

- source host: `46.21.81.186`
- source path: `/opt/amonora_bot/backups/pg/amonora_db_20260316-195700.sql.gz`

## Destination

- destination type: local machine off-host copy
- destination path:
  - originally created under `C:\Users\Skyfal\Downloads\amonora_offhost_backups\...`
  - current canonical local backup root:
    - `C:\Ops\Backups\amonora`

## Execution

Read-only / additive actions performed:

1. listed available dump artifacts on the core host
2. selected the latest timestamped `.sql.gz` dump in `/opt/amonora_bot/backups/pg/`
3. copied the file off-host via `scp`
4. verified the copied artifact locally
5. verified gzip integrity with `gunzip -t`

## Verification result

- copied file exists off-host: yes
- copied file size: `6749` bytes (`6.6K`)
- gzip integrity check: passed
- original server-side backup flow changed: no

## Success criteria result

- at least one PostgreSQL dump exists off-host: yes
- file is readable and non-empty: yes
- original backup flow on server unchanged: yes

## Rollback

No rollback was needed.

This task was additive only and did not modify:
- backup scripts
- timers
- services
- runtime config

## Next recommended step

- convert this into a repeatable operator command
- then a narrowly scoped automation path
- then extend the same model to VPN node artifacts
