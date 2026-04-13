# OFF-HOST BACKUP PLAN

Date: 2026-03-19
Method: documentation-only planning pass
Status: planned, no production changes performed

## Purpose

This document defines the first realistic off-host backup strategy for production.

It is intentionally a planning artifact only:
- no server changes were made;
- no provider features were enabled;
- no tools were installed;
- no data was uploaded anywhere.

## Inputs considered

This plan is based on already confirmed facts:
- production topology is three VPS:
  - core/backend: `46.21.81.186`
  - Germany VPN node: `213.108.20.34`
  - Estonia VPN node: `185.88.37.71`
- local backup artifacts exist on core and both VPN nodes;
- restore readiness is partial and fragile;
- no off-host replication is confirmed;
- provider snapshot support is absent on two hosts and paid-but-inactive on one host.

## Problem statement

Current backup posture is useful for some rollback and operator-error scenarios, but it is not sufficient for total host-loss protection.

The main operational gap is simple:
- backups exist;
- backups are mostly local;
- host-loss protection is therefore weak.

## Option analysis

### Option A — Provider snapshots

Description:
- use provider-managed instance backup or snapshot features where available.

Pros:
- simplest operational model;
- can protect more than just app artifacts;
- easiest to explain to one operator.

Cons:
- not uniformly available across the current three hosts;
- one host has no feature at all in the visible panel;
- one host has the feature only as a paid inactive add-on;
- retention and recovery semantics remain provider-specific;
- does not create a portable backup program.

Assessment:
- useful as a supplement;
- not strong enough as the primary cross-host strategy for the current topology.

### Option B — External object storage

Description:
- push backup artifacts from production hosts to object storage or S3-compatible storage using a controlled toolchain.

Candidate tools:
- `restic`
- `rclone`
- carefully scoped custom upload script

Pros:
- consistent across all three hosts;
- portable and provider-independent;
- retention can be designed explicitly;
- protects against whole-host loss if uploads complete successfully;
- fits the current artifact-based reality:
  - PostgreSQL dumps already exist
  - `3x-ui` backups already exist

Cons:
- needs credentials management;
- needs explicit tool/setup work later;
- needs monitoring and failure handling;
- config backups must be curated carefully to avoid secret sprawl.

Assessment:
- best primary long-term option for the current topology;
- most realistic path to one backup model that covers core and both VPN nodes.

### Option C — Remote backup host

Description:
- push artifacts to a separate VPS via `rsync`/`scp`.

Pros:
- conceptually simple;
- full operator control;
- no object-storage vendor dependency.

Cons:
- still leaves single-provider concentration risk if hosted nearby;
- introduces another machine to maintain;
- easier to build something ad hoc than something governed well;
- weaker long-term posture than portable object storage.

Assessment:
- acceptable fallback if object storage is temporarily impossible;
- not the best first target if we want a clean and durable off-host model.

## Selected approach

Recommended strategy: **hybrid with Option B as primary and Option A only as optional later supplement**.

### Decision

Primary recommendation:
- adopt **external object storage** as the canonical off-host backup destination.

Optional later supplement:
- if provider snapshot coverage becomes uniformly available and affordable, use it only as an additional coarse recovery layer, not as the sole backup program.

### Why this is the best fit

- it works across all three current hosts;
- it does not depend on uneven provider features;
- it matches the current backup reality, where important artifacts already exist on disk;
- it gives a clearer path to explicit retention than the current artifact accumulation model;
- it reduces host-loss risk without forcing immediate application redesign.

## Minimum required protected scope

### Core host

Must include:
- PostgreSQL dumps for `amonora_db`
- `/opt/amonora_bot/backups/pg/*`
- `/opt/amonora_bot/backups/amonora_db*.dump`
- `/opt/amonora_bot/backups/support_tickets*.json`
- `/opt/amonora_bot/backups/payments/*`
- `/opt/amonora_bot/backups/xui/*`
- `/opt/amonora_bot/backups/legacy-vpn/*`

Should include:
- selected app/runtime recovery materials under `/opt/amonora_bot/backups/dashboard/*`
- selected feature-flow rollback artifacts if still operationally relevant

Optional curated config layer:
- `nginx` config snapshots
- systemd unit snapshots
- env snapshots only if stored and transported in a secrets-safe way

### VPN nodes

Must include on each node:
- `/opt/3x-ui/db/x-ui.db`
- `/opt/3x-ui/backups/*`

Should include where present:
- `config.json` snapshots associated with node state

## Explicit exclusions for the first rollout

Do not include in the first off-host rollout:
- whole-repo mirroring as a substitute for backup
- raw home-directory bulk sync
- uncurated `/etc` dumps
- secrets copied into git-tracked documentation
- live database streaming replication design
- full-image backup assumptions without independent artifact export

## Proposed retention model

This is the minimum viable retention model for the first production rollout:

### PostgreSQL

- daily off-host copy of the latest dump
- keep `7` daily copies
- keep `4` weekly copies

### 3x-ui artifacts

- daily off-host copy of node backup artifacts
- keep `7` daily copies
- keep `4` weekly copies

### App-side JSON / operational recovery artifacts

- daily or event-driven upload, depending on how those artifacts are actually produced
- keep `7` daily copies
- keep `2` to `4` weekly copies

### Important note

This retention model is intentionally simple.
The first goal is not perfect backup economics.
The first goal is to stop relying on host-local storage alone.

## Minimal rollout plan

This section is planning only.
It is not an execution checklist yet.

### Phase 1 — Design freeze

1. Confirm the canonical destination type:
   - preferred: object storage bucket/container
2. Confirm naming convention:
   - host + asset class + timestamp
3. Confirm the exact protected paths per host
4. Confirm who owns credentials and where they will live outside git

Verification after phase:
- protected asset list is explicit;
- destination is chosen;
- no hidden operator-only assumptions remain.

### Phase 2 — Core-host first rollout

1. Introduce off-host upload only for existing PostgreSQL dump artifacts
2. Verify that uploaded artifacts are visible off-host
3. Verify naming and retention behavior on the destination
4. Verify that local dump flow remains unchanged

Why core first:
- `amonora_db` is the most critical single asset class;
- it gives the highest risk reduction first.

Verification after phase:
- at least one successful off-host PostgreSQL artifact exists;
- object naming is stable;
- failure mode is observable.

### Phase 3 — VPN node rollout

1. Add off-host copy for Germany node:
   - `x-ui.db`
   - `/opt/3x-ui/backups/*`
2. Add off-host copy for Estonia node:
   - `x-ui.db`
   - `/opt/3x-ui/backups/*`
3. Verify that each node’s artifacts remain distinguishable by host and date

Verification after phase:
- both nodes have visible off-host copies;
- node artifacts are not mixed together;
- at least one recent artifact per node is easy to identify.

### Phase 4 — Governance hardening

1. Add explicit retention enforcement
2. Add backup failure visibility:
   - log
   - status marker
   - simple operator check path
3. Update `RUNBOOK.md` with the real operator flow
4. Add restore-readiness follow-up against the new off-host artifacts

Verification after phase:
- retention is not accidental;
- operator can answer "did yesterday’s off-host backup succeed?" without guesswork;
- recovery assumptions are documented.

## Verification rules after later implementation

When this plan is eventually executed, the operator must verify:
- artifact exists off-host;
- artifact belongs to the expected host;
- artifact timestamp is current enough;
- artifact is non-empty and plausibly valid;
- retention is behaving as intended;
- failure is visible when upload does not succeed.

## Failure scenarios

### Backup upload fails

Expected handling:
- local backup remains untouched;
- failure is logged and visible;
- no silent success state is accepted.

### Destination storage unavailable

Expected handling:
- do not delete local artifacts;
- surface failure explicitly;
- retry policy must be documented before rollout.

### Partial backup

Examples:
- PostgreSQL copied, but VPN artifacts not copied
- one node copied, second node failed

Expected handling:
- report asset-class level success/failure separately;
- do not claim "backup succeeded" as a single boolean without detail.

### Corrupt or unusable artifact

Expected handling:
- later restore-readiness pass must include artifact validation assumptions;
- off-host copy presence alone must not be treated as proof of recoverability.

## Rollback posture for the rollout itself

Because this plan proposes additive backup uploads rather than destructive changes, rollback for the first implementation should be simple:
- disable the new upload path;
- keep existing local backup behavior unchanged;
- retain documentation of what was attempted and what failed.

The first implementation should avoid changing:
- existing local dump generation;
- current restore scripts;
- existing node backup behavior;
- current deploy/runtime topology.

## Restore assumptions this plan would improve

If implemented successfully, this plan would improve:
- protection against total loss of a single VPS;
- portability of DB and node-state recovery artifacts;
- operator confidence before future production changes.

## What this plan would not guarantee

Even after implementation, this plan would not by itself guarantee:
- instant full-platform rebuild;
- application-consistent full-machine snapshots;
- secret/config correctness unless config scope is curated carefully;
- proven restore success without a later restore validation pass.

## Cost and complexity view

### Lowest operational effort

- provider snapshots

Problem:
- not uniformly available now.

### Best long-term fit

- object storage

Reason:
- one model for all hosts;
- portable;
- explicit retention possible.

### Simplest fallback if object storage is blocked

- remote backup host

Reason:
- still better than local-only storage;
- but should be treated as a compromise, not the ideal target.

## Recommended next execution order

When the team is ready to move from planning to execution, the safest order is:

1. create a dedicated execution task for core PostgreSQL off-host copy only
2. implement and verify core-host path
3. implement and verify Germany node path
4. implement and verify Estonia node path
5. add retention and failure visibility
6. run a restore-readiness follow-up against the new off-host layer

## Final recommendation

Do not treat provider snapshots as the main plan.

The current infrastructure evidence supports this recommendation:
- provider coverage is uneven;
- one host has paid-but-inactive backup only;
- two hosts do not expose usable provider backup in the visible panel.

The most realistic first production change candidate is:
- **introduce external off-host artifact backup with a narrow initial scope, starting from PostgreSQL dumps on the core host**.

That is the smallest production change that materially improves safety for everything that comes after it.
