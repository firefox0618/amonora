# RESTORE READINESS

Date: 2026-03-19
Method: read-only inspection of live artifacts and restore-related scripts
Status: completed

## Summary

Restore readiness is partial.

What is real:
- PostgreSQL restore scripts exist on the core host;
- PostgreSQL dump artifacts exist on the core host;
- `3x-ui` backup artifacts exist on both VPN nodes.

What is still weak:
- restore flow depends on host-specific and time-specific assumptions;
- some restore steps are clearly manual or operator-knowledge driven;
- `3x-ui` restore path is not backed by an explicit production-side restore script from this pass;
- end-to-end restore confidence is not yet strong enough for aggressive cleanup or high-risk migration work.

## Confirmed restore artifacts and scripts

### Core host

Host:
- `46.21.81.186`

Confirmed restore-related scripts:
- `/root/amonora_restore_db.sh`
- `/root/amonora_restore_part2.sh`

Confirmed backup inputs present on disk:
- `/opt/amonora_bot/backups/amonora_db_2026-03-16.dump`
- `/opt/amonora_bot/backups/pg/amonora_db_.sql.gz`
- `/opt/amonora_bot/backups/pg/amonora_db_20260316-195700.sql.gz`
- `/opt/amonora_bot/backups/support_tickets_2026-03-16.json`

Other operational backup materials present:
- dashboard/nginx tarballs and config snapshots under `/opt/amonora_bot/backups/dashboard`
- point-in-time product flow backups under `/opt/amonora_bot/backups/device-flow-20260317`
- payments/support/legacy-vpn/xui JSON artifacts under `/opt/amonora_bot/backups/...`

### Germany VPN node

Host:
- `213.108.20.34`

Confirmed restore-relevant backup inputs:
- `/opt/3x-ui/backups/x-ui.db.`
- `/opt/3x-ui/backups/x-ui.db.20260316-205700`

No dedicated restore script was confirmed from this pass.

### Estonia VPN node

Host:
- `185.88.37.71`

Confirmed restore-relevant backup inputs:
- `/opt/3x-ui/backups/config.json.20260317-220759`
- `/opt/3x-ui/backups/x-ui.db.`
- `/opt/3x-ui/backups/x-ui.db.20260316-195700`
- `/opt/3x-ui/backups/x-ui.db.20260317-220759`

No dedicated restore script was confirmed from this pass.

## High-level PostgreSQL restore path

The current restore flow on the core host is conceptually this:

1. obtain or copy the expected PostgreSQL dump onto the core host;
2. ensure the PostgreSQL role and database exist;
3. run `pg_restore` into `amonora_db`;
4. run basic sanity checks against key tables;
5. continue with app/runtime-side recovery steps if needed.

This is a real restore path, but it is not yet a clean canonical recovery procedure.

## High-level 3x-ui restore path

The currently visible restore path for `3x-ui` is mostly inferred from the backup artifacts:

1. identify the correct node backup in `/opt/3x-ui/backups`;
2. recover `x-ui.db` and, where available, matching config material;
3. return the panel/runtime to a working `3x-ui` state;
4. validate that the backend-facing XUI integration still matches the node.

This path is only partially documented from the current pass.
The backup inputs are real, but explicit restore mechanics are not yet written down on the nodes in the same way PostgreSQL restore is.

## What is explicitly covered

- PostgreSQL restore to the main database is covered at a script level;
- existence checks and sanity-check counts are part of the DB restore script flow;
- local backup artifacts for `3x-ui` exist and could support manual recovery.

## What looks fragile

- the PostgreSQL restore scripts depend on very specific artifact names rather than a generic latest-backup selection flow;
- the restore path appears tied to a historical migration/recovery moment, not yet a hardened reusable disaster-recovery procedure;
- the restore scripts depend on external assumptions that are not yet canonically documented;
- there is evidence of operator knowledge embedded in scripts rather than isolated in a safe documented process;
- `3x-ui` recovery appears to rely more on manual operator judgment than on a clean scripted restore flow.

## What is not covered with confidence

- restoring to a clean state after total host loss;
- restoring full app runtime materials in a canonical, repeatable order;
- restoring env/systemd/nginx with the same confidence as database artifacts;
- cross-host or off-host recovery;
- a tested full restore drill from backup to working production state.

## Restore-confidence gaps

- restore scripts contain hidden prerequisites and should not be treated as self-explanatory;
- script presence does not prove successful recovery under current runtime conditions;
- some restore logic is time-bound to specific filenames and older migration context;
- `3x-ui` restore governance is weaker than PostgreSQL restore governance;
- the current recovery model is still partly "operator memory" rather than stable operational doctrine.

## Practical conclusion

The project is no longer in a "no restore path at all" situation.
However, restore readiness is not yet mature enough to assume safe rollback from any major change.

The realistic posture right now is:
- DB restore path: partially real, partially fragile
- `3x-ui` restore path: artifact-backed, but still underdocumented
- full platform restore: not yet confidently documented end-to-end

## Recommended next tasks

- create a backup governance and retention map;
- harden restore documentation into a canonical high-level ops procedure;
- remove hidden assumptions from restore paths;
- do not rely on current restore readiness as a substitute for explicit pre-change backups.
