# AGENTS.md

## Purpose
This repository contains the Amonora ecosystem, with Amonora Connect as the current primary product.
The repository includes product code, operational code, documentation, and transitional legacy/new layers.

Your job is to work carefully, preserve system integrity, and prefer explicit plans over broad refactors.

## Read first
Before making any significant change, read these files in order:

1. `documentation/PROJECT_OVERVIEW.md`
2. `documentation/ARCHITECTURE.md`
3. `documentation/DOMAIN.md`
4. `documentation/REPO_RULES.md`
5. `documentation/RUNBOOK.md`
6. `documentation/FEATURES.md`
7. `documentation/TEAM_CONTEXT.md`
8. `documentation/PUBLIC_SURFACES.md`

Then read AI context files:

9. `documentation/ai/PROJECT_CONTEXT.md`
10. `documentation/ai/STACK_RULES.md`
11. `documentation/ai/PHASES.md`
12. `documentation/ai/STATE.md`

## Core working rules
- Do not assume the codebase is fully centralized. Domain logic is still distributed across `backend`, `bot`, `dashboard`, and `support_bot`.
- Do not treat `dashboard` as fully legacy. It still contains active backend/API responsibilities.
- Do not remove old UI flows from `dashboard` unless coverage in `dashboard_v2` is explicitly confirmed.
- Do not move files or directories as part of unrelated feature work.
- Do not change runtime paths, ports, service names, or deployment assumptions without updating `documentation/RUNBOOK.md`.
- Do not introduce secret values into the repository. Use `PRIVATE_ACCESS.template.md` patterns, never real credentials.
- Prefer small, reviewable, reversible changes.

## Execution protocol
For any non-trivial task:

1. Restate the task.
2. Identify affected components and files.
3. Explain risks and dependencies.
4. Propose a step-by-step plan.
5. Only then implement changes.
6. After changes, summarize:
   - files changed
   - behavior changed
   - tests added/updated
   - manual checks required
   - follow-up risks

## Documentation protocol
When a task changes architecture, domain behavior, repo rules, operations, or public surfaces, update the relevant documentation.

At minimum, consider whether to update:
- `documentation/ARCHITECTURE.md`
- `documentation/DOMAIN.md`
- `documentation/FEATURES.md`
- `documentation/RUNBOOK.md`
- `documentation/REPO_RULES.md`
- `documentation/ai/STATE.md`

## Task handling
Do not work from vague goals like “improve system” or “refactor bot”.
Convert work into atomic tasks with:
- context
- scope
- constraints
- acceptance criteria
- validation steps

Use `documentation/ai/TASKS/*.md` as the source of truth for active implementation tasks.

## Review mode
When asked to review:
- do not rewrite immediately
- first list findings by severity
- identify regressions, missing tests, architectural drift, and unclear assumptions

## If context is incomplete
State what is known, what is inferred, and what needs verification from runtime, production, or ops config.
Do not present guesses as confirmed facts.
