# BACKUP VERIFICATION

Date: 2026-03-19
Method: read-only live inspection
Status: completed

## Scope

This pass verifies what backup artifacts and backup-related runtime evidence actually exist in production.
It does not prove full restore readiness by itself and does not create or modify any backup.

## Summary

- backup artifacts are confirmed to exist for PostgreSQL and `3x-ui`;
- local backup storage is confirmed on the core host and both VPN nodes;
- evidence of recent backup files exists, but continuous automated rotation is not yet fully proven;
- off-server backup replication was not confirmed from this pass;
- restore readiness is only partially evidenced:
  - database restore scripts exist on the core host;
  - no full documented restore drill was confirmed in this pass.

## Core host: PostgreSQL and app-side artifacts

Host:
- `46.21.81.186`
- role: core/backend

Confirmed backup paths:
- `/opt/amonora_bot/backups`
- `/opt/amonora_bot/backups/pg`

Confirmed artifacts:
- `/opt/amonora_bot/backups/amonora_db_2026-03-16.dump`
- `/opt/amonora_bot/backups/pg/amonora_db_.sql.gz`
- `/opt/amonora_bot/backups/pg/amonora_db_20260316-195700.sql.gz`
- `/opt/amonora_bot/backups/support_tickets_2026-03-16.json`
- `/opt/amonora_bot/backups/payments/payment_cleanup_backup_20260317.json.gz`

Observed characteristics:
- backup artifacts exist locally on the production core host;
- PostgreSQL dump evidence includes both:
  - custom-format `.dump`
  - compressed `.sql.gz`
- the visible timestamp pattern suggests point-in-time/manual or scripted dump creation around `2026-03-16` and `2026-03-17`;
- no active dedicated backup timer or cron entry for app/database dumps was confirmed in live system timers or root crontab.

Restore-related evidence:
- restore scripts exist on the core host:
  - `/root/amonora_restore_db.sh`
  - `/root/amonora_restore_part2.sh`
- these scripts indicate that database restore has at least been operationally considered;
- restore confidence is still partial because this pass did not execute or validate a restore.

Important risk:
- backup/restore operational material exists outside the repo-controlled ops layer;
- this increases risk of drift between documented rollback flow and real server-side recovery steps.

## Germany VPN node: 3x-ui backups

Host:
- `213.108.20.34`
- role: primary VPN node

Confirmed backup path:
- `/opt/3x-ui/backups`

Confirmed artifacts:
- `/opt/3x-ui/backups/x-ui.db.`
- `/opt/3x-ui/backups/x-ui.db.20260316-205700`

Observed characteristics:
- local `3x-ui` database backup artifacts exist;
- visible artifacts are dated `2026-03-16`;
- no dedicated backup timer/cron entry was confirmed from the inspected runtime output;
- no off-server replication target was confirmed.

Interpretation:
- backup evidence exists, but it looks more like manual or ad hoc backup than a clearly proven recurring backup system.

## Estonia VPN node: 3x-ui backups

Host:
- `185.88.37.71`
- role: reserve VPN node

Confirmed backup path:
- `/opt/3x-ui/backups`

Confirmed artifacts:
- `/opt/3x-ui/backups/config.json.20260317-220759`
- `/opt/3x-ui/backups/x-ui.db.`
- `/opt/3x-ui/backups/x-ui.db.20260316-195700`
- `/opt/3x-ui/backups/x-ui.db.20260317-220759`

Observed characteristics:
- local `3x-ui` database and config backup artifacts exist;
- visible timestamps include `2026-03-16` and `2026-03-17`;
- this is stronger evidence than on the Germany node because both DB and config backup artifacts are present;
- no dedicated backup timer/cron entry was confirmed from the inspected runtime output;
- no off-server replication target was confirmed.

## What is confirmed

- PostgreSQL data has local dump artifacts on the core host;
- `3x-ui` data has local backup artifacts on both VPN nodes;
- backup naming uses timestamp suffixes in at least part of the current flow;
- restore scripts exist for PostgreSQL on the core host;
- the current backup posture is at least partially real and not purely theoretical.

## What is not confirmed

- a recurring automated PostgreSQL dump schedule;
- a recurring automated `3x-ui` backup schedule on both VPN nodes;
- retention rules for local backup cleanup;
- replication of backups to another host, object storage, or provider snapshot flow;
- a tested end-to-end restore drill;
- whether all critical env/nginx/systemd materials are backed up systematically or only manually.

## Backup confidence gaps

- local-only backups do not protect against total host loss;
- backup files may exist without guaranteed recurring automation;
- restore scripts existing on disk do not equal restore process readiness;
- backup procedures are still partly operational knowledge, not yet fully consolidated in canonical ops docs;
- server-side recovery scripts may contain sensitive operational assumptions and require separate hardening/review.

## Practical conclusion

Current backup posture is better than "no backups", but not yet strong enough to justify aggressive cleanup, migration, or high-risk refactors.

The project currently has:
- real backup artifacts;
- partial restore evidence;
- incomplete backup governance.

That means future risky work should still follow:
- explicit pre-change backup;
- explicit rollback note;
- no assumption that background backup automation will save the situation automatically.

## Recommended next tasks

- verify whether PostgreSQL dumps are generated by a repeatable server-side script or only manually;
- verify whether `3x-ui` backups are created by container/panel behavior or by operator action;
- document the canonical restore flow in ops docs without exposing secrets;
- do a restore-readiness planning pass before major cleanup or migration work.
