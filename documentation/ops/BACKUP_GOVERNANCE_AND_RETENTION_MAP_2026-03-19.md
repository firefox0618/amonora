# BACKUP GOVERNANCE AND RETENTION MAP

Date: 2026-03-19
Method: read-only live inspection
Status: completed

## Purpose

This document maps the current governance posture of backups:
- what is protected;
- where artifacts live;
- what seems to trigger them;
- whether retention is visible;
- whether storage is local-only or replicated;
- where the process still depends on operator memory.

## Overall conclusion

Backup governance is partial and uneven.

The project has real backup artifacts across core and VPN nodes, but the operational model is not yet strongly centralized or consistently automated.

What looks solid:
- backup artifacts exist for core PostgreSQL and for node-side `3x-ui`;
- backup classes are already separated by domain on the core host;
- there is at least partial restore thinking on the core host.

What looks weak:
- recurring automation is not clearly proven for most project-specific backups;
- retention appears incidental rather than governed;
- off-host replication is not confirmed;
- operator-memory dependencies remain high.

## Asset class map

### PostgreSQL

- asset class: primary application database
- artifact locations:
  - `/opt/amonora_bot/backups/amonora_db_2026-03-16.dump`
  - `/opt/amonora_bot/backups/pg/amonora_db_.sql.gz`
  - `/opt/amonora_bot/backups/pg/amonora_db_20260316-195700.sql.gz`
  - additional dump artifacts also exist under `/root`
- trigger type:
  - confirmed: script/manual history exists
  - not confirmed: recurring timer/cron specifically for project DB dumps
- frequency:
  - inferred: point-in-time/manual or migration-time dumps
  - confirmed recurring schedule: no
- retention evidence:
  - limited visible date range
  - no confirmed cleanup policy
  - no confirmed rotation policy
- storage class:
  - confirmed: local only on core host
  - off-host: not confirmed
- restore dependency:
  - server-side restore script + operator knowledge
- confidence:
  - medium

### Support/payment/operational JSON artifacts

- asset class:
  - support ticket snapshots
  - payment cleanup snapshot
  - legacy-vpn/xui JSON state artifacts
- artifact locations:
  - `/opt/amonora_bot/backups/support_tickets_2026-03-16.json`
  - `/opt/amonora_bot/backups/payments/payment_cleanup_backup_20260317.json.gz`
  - `/opt/amonora_bot/backups/legacy-vpn/...`
  - `/opt/amonora_bot/backups/xui/...`
- trigger type:
  - likely manual or one-off script-driven
  - recurring governance not confirmed
- frequency:
  - unknown
- retention evidence:
  - timestamped point-in-time artifacts exist
  - no confirmed cleanup or retention policy
- storage class:
  - local only
- restore dependency:
  - mostly operator/manual interpretation
- confidence:
  - low

### Dashboard / nginx / app-side snapshots

- asset class:
  - dashboard tarballs
  - nginx config snapshots
  - feature-flow backup folders
- artifact locations:
  - `/opt/amonora_bot/backups/dashboard/...`
  - `/opt/amonora_bot/backups/device-flow-20260317/...`
- trigger type:
  - appears manual or ad hoc script-driven
- frequency:
  - unknown
- retention evidence:
  - point-in-time naming exists
  - overwrite/cleanup behavior not confirmed
- storage class:
  - local only
- restore dependency:
  - operator memory / manual file rollback
- confidence:
  - low

### 3x-ui DB and config: Germany node

- asset class:
  - node panel DB
- artifact locations:
  - `/opt/3x-ui/backups/x-ui.db.`
  - `/opt/3x-ui/backups/x-ui.db.20260316-205700`
- trigger type:
  - unknown
  - could be panel-driven, container-driven, or operator-created
- frequency:
  - not confirmed
- retention evidence:
  - two artifacts visible
  - both from the same date window
  - no confirmed cleanup/rotation policy
- storage class:
  - local only on Germany node
- restore dependency:
  - manual/operator knowledge
- confidence:
  - low

### 3x-ui DB and config: Estonia node

- asset class:
  - node panel DB
  - panel config snapshot
- artifact locations:
  - `/opt/3x-ui/backups/config.json.20260317-220759`
  - `/opt/3x-ui/backups/x-ui.db.`
  - `/opt/3x-ui/backups/x-ui.db.20260316-195700`
  - `/opt/3x-ui/backups/x-ui.db.20260317-220759`
- trigger type:
  - unknown
  - likely operator-driven or panel-local rather than centrally scheduled
- frequency:
  - not confirmed
- retention evidence:
  - at least two dated generations visible
  - no confirmed cleanup/rotation policy
- storage class:
  - local only on Estonia node
- restore dependency:
  - manual/operator knowledge
- confidence:
  - low to medium

## Trigger model

## Clearly confirmed

- no project-specific root cron entries were confirmed on the inspected hosts;
- no project-specific backup timer was confirmed for DB dumps or `3x-ui` backups;
- general OS timers like `dpkg-db-backup.timer` exist but do not count as application backup governance.

## Partially evidenced

- server-side scripts exist on the core host for restore and deployment;
- backup artifacts and naming patterns show that manual/scripted backup actions have happened;
- `3x-ui` backup files may be created by operator action or panel/container behavior, but this is not yet proven.

## Unknown

- exact ownership of recurring PostgreSQL backup creation;
- exact ownership of recurring `3x-ui` backup creation;
- whether any backup generation is tied to deploy/reconcile flows automatically;
- whether provider-level snapshots are part of the real backup model.

## Retention and rotation map

## Confirmed evidence

- timestamp-based naming is used in several backup classes;
- some asset classes keep more than one generation;
- both VPN nodes show retained historical `3x-ui` artifacts rather than a single current file.

## Not confirmed

- formal retention duration;
- max generations kept;
- automatic cleanup based on age;
- storage pressure management;
- distinction between long-lived backups and temporary migration artifacts.

## Practical interpretation

Current retention looks like "keep what was created" rather than "managed lifecycle policy".

## Storage class map

- core PostgreSQL and app artifacts: local only confirmed
- Germany `3x-ui` artifacts: local only confirmed
- Estonia `3x-ui` artifacts: local only confirmed
- off-host copies:
  - not confirmed from tracked runtime inspection
  - some restore/deploy history suggests cross-host file movement has happened operationally, but that is not a governed backup destination

## Operator-memory dependencies

The following areas still depend heavily on operator knowledge:

- which dump is the correct one to restore from;
- which node-side `3x-ui` backup is authoritative;
- how `3x-ui` should be restored safely after DB/config replacement;
- how app/runtime config snapshots should be applied in a real rollback;
- which server-side scripts are historical one-offs versus reusable production recovery tools.

## Governance gaps

- no clearly confirmed centralized backup ownership model;
- no clearly confirmed recurring schedule for project backups;
- no clearly confirmed retention or cleanup policy;
- no clearly confirmed off-host protection;
- restore readiness depends partly on scripts that embed hidden assumptions;
- documentation is improving, but the operational model is still not yet fully canonical.

## Confidence snapshot

- PostgreSQL backup governance: medium-low
- PostgreSQL restore governance: medium-low
- `3x-ui` backup governance: low
- `3x-ui` restore governance: low
- app/runtime snapshot governance: low
- end-to-end backup program maturity: low to medium

## Practical rule for now

Treat the current backup system as:
- real enough to be useful;
- not mature enough to be trusted blindly.

Before risky production changes:
- create explicit pre-change backups;
- record what was backed up;
- record rollback intent;
- do not assume background governance will cover missing steps automatically.

## Recommended next tasks

- document a canonical high-level backup ownership model;
- document a canonical high-level restore procedure;
- separate reusable recovery scripts from historical migration scripts;
- verify whether any provider snapshots or off-host backup flows exist;
- define retention policy explicitly instead of relying on artifact accumulation.
