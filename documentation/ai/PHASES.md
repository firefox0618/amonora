# PHASES.md

## Phase 1 — Documentation stabilization
Goal:
Create a trustworthy canonical documentation layer for the project.

Includes:
- project overview
- architecture
- domain
- repo rules
- runbook
- feature inventory
- team/public surface context

Status:
Mostly complete

## Phase 2 — AI operating layer
Goal:
Allow Codex/AI agents to work safely from structured context.

Includes:
- AGENTS.md
- AI context files
- task templates
- state tracking
- implementation protocol

Status:
Active

Current focus:
- introduce AI task workflow
- keep changes plan-first and documentation-aware
- support stabilization of the current product core

## Phase 3 — Repository normalization
Goal:
Reduce ambiguity in repo structure without risky broad rewrites.

Includes:
- clarify docs vs temporary docs
- test organization
- legacy/runtime artifact cleanup
- identify true active modules
- define migration boundaries

Status:
Planned

Primary intent:
- reduce ambiguity carefully
- do not destabilize the working VPN and admin contours during cleanup

## Phase 4 — Domain consolidation
Goal:
Reduce logic spread across components where safe and justified.

Includes:
- identify duplicated business rules
- centralize selected domain logic
- preserve working external flows
- document boundaries before moving code

Status:
Planned

Primary intent:
- centralize only where justified
- avoid broad rewrites before the current core is operationally stable

## Phase 5 — Feature delivery with controlled workflow
Goal:
Deliver new work through atomic tasks, review loops, and documentation-aware implementation.

Includes:
- task-based delivery
- structured review
- state tracking
- feature status updates

Status:
Planned

Current sequencing note:
- first stabilize the core and VPN layer
- then introduce the next adjacent product layer through controlled tasks
