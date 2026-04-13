# NEXT_STAGE_BACKLOG

## Purpose
Capture the next short, controlled stage after the current documentation + hardening checkpoint.

## Current position
The project already has:
- canonical documentation
- AI workflow and task layer
- runtime and backup reality mapping
- baseline diff audit
- first auth/payment/API hardening seams
- safe/review-needed snapshot checkpoints

The next stage should continue strengthening the system without jumping into broad refactors.

## Priority order

### 1. Historical docs cleanup
Goal:
Reduce confusion inside the older `documentation/` layer without deleting useful context.

Focus:
- keep the canonical layer clearly primary
- mark historical/supporting docs more explicitly
- reduce ambiguity between active docs and historical/reference docs

Out of scope:
- deleting useful historical material blindly
- moving runtime-sensitive files
- rewriting the whole documentation system again

### 2. Next API seam only if clearly justified
Goal:
Add one more load-bearing API seam only if it has a clear payoff for `dashboard/ui`.

Current protected seams:
- auth/session
- payment finalization
- payment confirmation idempotency
- `overview`
- `payments`
- `users`
- `support`

Rule:
If there is no clearly dominant next seam, it is acceptable to stop the API hardening pass here for now.

### 3. Infra-hardening backlog
Goal:
Record the next larger ops block without implementing it yet.

Known issues to carry forward:
- off-host backup / provider snapshots are absent or unconfirmed
- host-loss confidence remains low
- restore path exists but remains fragile
- backup governance is weaker than the presence of backup artifacts suggests

This should be treated as a planned ops-hardening track, not as a small immediate cleanup step.

### 4. No big refactors yet
Rule:
Do not jump into broad structural refactors immediately after this stage.

Prefer:
- small safe/review-needed improvements
- one seam at a time
- documented scope before implementation
- changes that can be validated quickly

## Recommended next choices

### Option A — Continue small hardening
- do historical docs cleanup
- then decide whether one more API seam is worth it

### Option B — Pause API hardening and prepare ops work
- do historical docs cleanup
- then write a focused infra-hardening plan for off-host backup and restore confidence

## Suggested interpretation
The project is no longer in a discovery phase.
It is in a controlled strengthening phase.

That means:
- keep momentum
- avoid chaotic cleanup
- prefer checkpoints over broad rewrites
- only open larger refactors after the next stage is explicitly defined
