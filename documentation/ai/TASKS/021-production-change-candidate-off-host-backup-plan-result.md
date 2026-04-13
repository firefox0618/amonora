# TASK 021 — Production change candidate: off-host backup plan result

## Status
Completed

## Outcome

A documentation-only production planning pass was completed.

Output created:
- `documentation/ops/OFF_HOST_BACKUP_PLAN.md`

## Main decision

Selected direction:
- primary strategy: external object storage / S3-compatible off-host backup
- optional later supplement: provider snapshots only as an additional coarse recovery layer, not the primary backup model

## Why this was chosen

- provider backup support is uneven across the three production hosts;
- local artifacts already exist and can be exported without redesigning the application;
- object storage gives a single cross-host model for:
  - PostgreSQL dumps
  - `3x-ui` DB/config artifacts
  - selected operational recovery artifacts

## Planned first execution target

The recommended first real production change is intentionally narrow:
- start with off-host copy of PostgreSQL dump artifacts from the core host

Reason:
- highest safety gain for the smallest first operational step

## Explicitly not done

- no SSH changes
- no package installation
- no provider feature activation
- no cron/systemd edits
- no upload to any backup destination

## Next recommended step

Create a dedicated execution task for:
- core PostgreSQL off-host backup rollout

Only after that succeeds:
- extend the same off-host model to Germany and Estonia VPN node artifacts
