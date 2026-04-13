# HISTORICAL_SUPPORTING_MAP

## Purpose
Clarify which root-level files in `documentation/` remain useful as supporting or historical references, but are not part of the canonical current-state documentation layer.

## Canonical current-state docs
These remain the primary source of truth for the project as it exists now:

- `PROJECT_OVERVIEW.md`
- `ARCHITECTURE.md`
- `DOMAIN.md`
- `REPO_RULES.md`
- `RUNBOOK.md`
- `FEATURES.md`
- `TEAM_CONTEXT.md`
- `PUBLIC_SURFACES.md`
- `INDEX.md`

## Supporting reference docs
These can still be useful, but should be read as supporting material rather than as the primary description of current architecture/runtime truth.
They now live under `documentation/supporting/`:

- `supporting/bot-flow.md`
- `supporting/dashboard.md`
- `supporting/deployment.md`
- `supporting/infrastructure.md`
- `supporting/operations-runbook.md`
- `supporting/product.md`
- `supporting/support-bot.md`
- `supporting/user-guide.md`
- `supporting/panel-ui-deep-dive.md`
- `supporting/optimization-report.md`

## Dated historical snapshots
These are useful as dated audits or planning snapshots and should be read with their date/context in mind.
They now live under `documentation/archive/snapshots/`:

- `archive/snapshots/system-audit-2026-03-19.md`
- `archive/snapshots/status-and-next-steps-2026-03-19.md`
- `archive/snapshots/git-stabilization-2026-03-19.md`
- `archive/snapshots/STAGE_CHECKPOINT_2026-03-19.md`

## Legal and policy docs
These remain active reference docs, but they are not architecture/runtime canon:

- `cookie-policy.md`
- `legal-compliance.md`
- `license-notice.md`
- `privacy-policy.md`
- `refunds-support-policy.md`
- `terms-of-service.md`

## Reading rule
If a supporting or historical document conflicts with the canonical current-state layer, treat the canonical layer as primary unless the older document is intentionally being used as:
- legal/policy reference
- historical snapshot
- supporting deep dive
