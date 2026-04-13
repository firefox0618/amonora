# TASK 008 RESULT — Backup governance and retention map

## Status
Completed

## Outcome

Backup governance and retention posture was mapped in read-only mode from live servers.

## What was confirmed

- major backup asset classes are visible on the core host and both VPN nodes;
- core backups are already grouped by domain, not stored as a single dump pile;
- project-specific backup automation is not clearly proven from timers/cron;
- off-host replication is still not confirmed;
- retention is visible as artifact accumulation, not as a clearly governed policy.

## What was observed

- PostgreSQL has the strongest artifact and recovery posture, but governance is still incomplete;
- `3x-ui` artifacts exist on both nodes, but lifecycle ownership remains unclear;
- several backup classes look manual or one-off rather than policy-driven;
- operator-memory dependency remains one of the main governance risks.

## Main outputs

- canonical governance doc:
  - `documentation/ops/BACKUP_GOVERNANCE_AND_RETENTION_MAP_2026-03-19.md`
- clarified operational posture:
  - backup is real
  - governance is partial
  - retention is weakly defined

## Follow-up still needed

- canonical backup ownership model;
- retention/cleanup policy definition;
- off-host backup verification;
- hardening of operator-dependent restore/backup flows.
