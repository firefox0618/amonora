# STACK_RULES.md

## General principles
- Make the smallest change that solves the problem.
- Prefer explicitness over cleverness.
- Preserve current behavior unless the task explicitly changes it.
- Avoid repo-wide refactors during feature delivery.
- Keep docs and code aligned.

## Repository boundaries
- `backend` contains shared core/domain logic and models.
- `bot` contains primary user-facing bot flows.
- `support_bot` contains support-related bot flows.
- `dashboard` is not only legacy UI; it also contains active backend/API/admin logic.
- `dashboard/ui` is the newer admin UI layer.
- `landing` is a public-facing surface.
- `ops` contains operational/deployment/runtime assets.

## Change safety rules
- Do not assume code may be moved freely between components.
- Do not remove legacy paths until replacement coverage is verified.
- Do not change DB-facing logic without checking affected flows.
- Do not change admin flows without considering both `dashboard` and `dashboard/ui`.
- Do not change user access/payment/subscription logic without checking bot + admin impact.
- Do not alter operational assumptions without reflecting them in `RUNBOOK.md`.

## Documentation update rules
Update documentation when changing:
- architecture
- domain behavior
- public surfaces
- feature status
- operational procedures
- repo structure assumptions

## Secrets and access
- Never write secrets into tracked files.
- Use templates for secret-bearing documents.
- Treat `PRIVATE_ACCESS.md` as local-only and non-committable.

## Validation rules
For each task, define:
- what changed
- what should still work
- which tests cover the change
- which manual checks are needed

## Completion checklist
A task is not complete until:
- code changes are done
- obvious regressions were checked
- relevant tests were updated or added
- docs were reviewed for needed updates
- `documentation/ai/STATE.md` was updated if task status changed
