# TASK 007 — Documentation restructure

## Status
Completed

## Goal
Restructure the documentation tree so that canonical project docs, AI workflow docs, ops docs, VPN docs, product docs, strategy docs, business docs, and archived legacy docs are clearly separated.

## Why
The project currently contains many valuable markdown files, but they belong to different layers:
- current system truth
- operational procedures
- VPN-specific actions and safety rules
- product/interface vision
- long-term strategy
- business/growth materials
- legacy meta-docs

Without separation, documentation becomes noisy and harder for both humans and AI agents to use safely.

## Context
Relevant canonical docs:
- `documentation/INDEX.md`
- `documentation/PROJECT_OVERVIEW.md`
- `documentation/ARCHITECTURE.md`
- `documentation/DOMAIN.md`
- `documentation/REPO_RULES.md`
- `documentation/RUNBOOK.md`

Relevant AI docs:
- `AGENTS.md`
- `documentation/ai/PROJECT_CONTEXT.md`
- `documentation/ai/STACK_RULES.md`
- `documentation/ai/PHASES.md`
- `documentation/ai/STATE.md`

Relevant files to reorganize:
- ops-related docs
- vpn-related docs
- product vision/spec docs
- strategy/roadmap docs
- business/growth docs
- legacy index docs

## Current behavior
Documentation exists, but many files are still mixed at the same level and are not grouped by role.

## Desired behavior
Documentation should be grouped into:
- canonical core docs
- AI workflow docs
- ops docs
- VPN docs
- product docs
- strategy docs
- business docs
- archive

The index should reflect this structure.

## Scope
- create target folders if missing
- move and rename docs into their target locations
- create `documentation/INDEX.md`
- archive the old master index
- move temporary ecosystem drafts into archive
- create or reserve `documentation/strategy/PLATFORM_VISION.md`

## Out of scope
- rewriting the full content of all moved documents
- changing runtime behavior
- changing code structure
- implementing product features
- merging all strategy docs immediately

## Constraints
- preserve all useful content
- do not delete valuable docs during migration
- do not treat strategy/vision docs as current runtime truth
- keep canonical project docs at the root of `documentation/`

## Risks
- broken internal references after renaming/moving files
- temporary confusion between old and new paths
- duplicated content remaining in both active and archived locations

## Acceptance criteria
- target documentation folders exist
- specified files are moved to the correct locations
- `documentation/INDEX.md` exists and reflects the new structure
- `AMONORA_MASTER_INDEX.md` is archived
- ecosystem strategy drafts are archived
- canonical root docs remain easy to find

## Validation
Manual checks:
- verify moved files exist at their new paths
- verify `documentation/INDEX.md` points to valid locations
- verify no required canonical doc was misplaced
- verify archive contains old meta/strategy drafts, not active core docs

## Deliverables
- restructured documentation tree
- updated documentation index
- archived legacy index and old strategy drafts
- short summary of what was moved and why
