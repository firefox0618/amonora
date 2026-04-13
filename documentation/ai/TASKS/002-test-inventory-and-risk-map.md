# TASK 002 — Test inventory and risk map

## Status
Completed

## Goal
Map the current test surface, identify the most critical regression areas, and define where the project is underprotected.

## Why
The codebase contains multiple active contours and partially distributed domain logic. Safe feature work requires knowing which flows are protected by tests and which are not.

## Context
Relevant docs:
- `documentation/ARCHITECTURE.md`
- `documentation/DOMAIN.md`
- `documentation/RUNBOOK.md`
- `documentation/ai/STATE.md`

Relevant code areas:
- root test files
- `bot`
- `support_bot`
- `dashboard`
- `backend`

## Current behavior
Tests exist, but there is no canonical inventory describing critical vs secondary coverage.

## Desired behavior
The project should have a clear map of:
- existing tests
- critical protected flows
- weakly covered areas
- highest-risk gaps

## Scope
- inventory existing tests
- group tests by component and risk
- identify critical missing coverage
- suggest near-term testing priorities

## Out of scope
- broad test rewrites
- architecture changes
- production verification

## Constraints
- stay documentation-first
- do not rename or move tests unless explicitly needed
- distinguish confirmed coverage from inferred coverage

## Risks
- overstating what tests really cover
- missing cross-component regressions

## Acceptance criteria
- test inventory exists
- critical flows are listed
- weak areas are identified
- next testing priorities are defined

## Validation
Manual review:
- inventory matches actual files
- conclusions are tied to real flows

## Deliverables
- test inventory document
- risk map
- prioritized next test tasks
