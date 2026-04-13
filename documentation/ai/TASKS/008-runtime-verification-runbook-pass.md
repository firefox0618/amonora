# TASK 004 — Runtime verification runbook pass

## Status
Planned

## Goal
Verify `RUNBOOK.md` assumptions against actual runtime, deployment, `systemd`, and `nginx` state where possible.

## Why
The current runbook is already useful, but some statements are still based on repository inference and need stronger runtime confidence.

## Context
Relevant docs:
- `documentation/RUNBOOK.md`
- `documentation/ops/DEPLOY_RULES.md`
- `documentation/ops/ROLLBACK.md`
- `documentation/ops/CURRENT_STATE_2026-03-19.md`

Relevant code/config:
- `ops/systemd`
- `ops/nginx`
- runtime env assumptions

## Current behavior
Runbook entries are partially verified and partially inferred.

## Desired behavior
The runbook should clearly reflect:
- what is confirmed by runtime
- what is confirmed only by repo config
- what still requires production/server verification

## Scope
- compare runbook with repo configs
- tighten wording where needed
- mark unresolved runtime assumptions explicitly

## Out of scope
- infrastructure changes
- production edits
- changing service topology

## Constraints
- do not present guesses as confirmed facts
- prefer conservative wording where verification is incomplete

## Risks
- false confidence in operational details
- accidental drift between docs and real runtime

## Acceptance criteria
- runbook statements are reviewed
- verification status is clearer
- unresolved production questions are listed

## Validation
Manual review:
- each operational claim is either sourced, marked inferred, or marked unverified

## Deliverables
- updated runbook
- verification notes
- open ops verification checklist
