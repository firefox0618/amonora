# OFF-HOST BACKUP AND PROVIDER SNAPSHOT VERIFICATION

Date: 2026-03-19
Method: read-only server-side inspection plus read-only provider panel verification
Status: completed

## Summary

Local backup artifacts are confirmed.
Off-host protection is not confirmed from the currently available runtime and provider evidence.

Current realistic posture:
- core host: local backup confirmed, provider backup feature absent, off-host protection not confirmed
- Germany VPN node: local backup confirmed, provider backup feature available but not activated
- Estonia VPN node: local backup confirmed, provider backup feature absent, off-host protection not confirmed

No trustworthy evidence of:
- `restic`
- `borg`
- `rclone`
- `aws s3`
- `backblaze`
- scheduled remote `rsync`/`scp` backup replication

was confirmed from the inspected live systems.

## Host-by-host protection status

### Core host

- host: `46.21.81.186`
- local backup confirmed: yes
- provider snapshot confirmed: no
- off-host replication confirmed: no confirmed evidence
- confidence: low
- main gap:
  - provider backup/snapshot tab is absent in the panel, so host-loss protection is not proven beyond local storage

### Germany VPN node

- host: `213.108.20.34`
- local backup confirmed: yes
- provider snapshot confirmed: no active protection confirmed
- off-host replication confirmed: no confirmed evidence
- confidence: low
- main gap:
  - provider backup is offered as a paid add-on, but it is not activated; `3x-ui` backups appear local-only

Additional provider facts:
- backup feature exists in the panel;
- up to `7` copies are offered;
- automatic copying is offered as a feature;
- the feature requires separate purchase/activation;
- no existing snapshot or active provider backup was shown.

### Estonia VPN node

- host: `185.88.37.71`
- local backup confirmed: yes
- provider snapshot confirmed: no
- off-host replication confirmed: no confirmed evidence
- confidence: low
- main gap:
  - provider backup/snapshot tab is absent in the panel, so node-loss protection is not proven beyond local backup files on the node itself

## What was checked

The following evidence was inspected in read-only mode:
- server-side references to:
  - `scp`
  - `rsync`
  - `rclone`
  - `s3`
  - `restic`
  - `borg`
  - `ftp`
  - `sftp`
- likely backup tool/config directories under:
  - `/root`
  - `/home`
  - `/etc`
  - `/opt`
  - `/usr/local`
- previously confirmed backup directories on core and VPN nodes

## What was observed

- server-side searches did not reveal a clear, intentional off-host replication flow;
- some matches were false positives from dependencies, cached files, package metadata, or unrelated runtime files;
- no reliable evidence of a real object-storage or remote-backup toolchain was found;
- provider panel review showed:
  - no backup tab for `46.21.81.186`;
  - no backup tab for `185.88.37.71`;
  - paid-but-not-enabled backup feature for `213.108.20.34`.

## What is confirmed

- local backup artifacts exist on the core host;
- local `3x-ui` backup artifacts exist on both VPN nodes;
- current tracked operational knowledge does not prove active off-host backup governance for any of the three production hosts.

## What is not confirmed

- whether provider-side full-server recovery exists for `213.108.20.34` once the paid add-on is activated;
- whether provider backup coverage, once purchased, applies to full instance or only a disk/volume;
- whether any hidden provider-side snapshot retention exists outside the visible UI for the other two hosts;
- whether any external object storage or remote backup destination exists;
- whether host-loss recovery is actually covered by anything beyond local disk artifacts.

## Host-loss recovery gaps

- if the core host is fully lost, local PostgreSQL dumps on that host alone are not sufficient protection;
- if a VPN node is fully lost, node-local `3x-ui` backups on that same host do not prove recoverability;
- provider-side host-loss protection is absent or inactive across all three known production hosts;
- without confirmed provider snapshots or external replication, the current safety posture against total host loss remains weak.

## Practical conclusion

The project currently has local backup evidence, but no confirmed active off-host protection for any of the three known production hosts.

That means:
- backup posture is useful for operator mistakes and some partial rollback cases;
- backup posture is not yet proven strong against total host loss;
- current provider evidence does not justify claiming real disaster-recovery coverage.

## Required next verification

The remaining unknowns can only be closed by further read-only verification if the team later enables provider backup on the Germany node or acquires any other off-host backup mechanism:
- whether paid provider backup for `213.108.20.34` is ever activated;
- whether that protection covers full instance or disk-only recovery;
- whether any external replication path is later introduced.

## Recommended next tasks

- test inventory and risk map after ops-safety contour is fully understood;
- backup governance hardening only after an off-host protection path is introduced or intentionally accepted as absent.
