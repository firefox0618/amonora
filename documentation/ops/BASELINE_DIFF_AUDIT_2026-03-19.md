# BASELINE_DIFF_AUDIT_2026-03-19

## Purpose
Capture a read-only diff audit between the current repository line and `origin/codex/server-baseline-20260319`.

## Important note
`develop` and `origin/codex/server-baseline-20260319` do not have a merge base in the current local git history.
This audit therefore reflects a direct tree-to-tree comparison, not a normal ancestry-based branch diff.

This document also reflects branch-level differences only.
It does not include additional uncommitted local workspace changes.

## High-level conclusion
The main divergence is not small clutter.
It is a new active admin/runtime contour built around:
- `dashboard/ui`
- `dashboard/v2_data.py`
- ops wiring required to run and expose that contour

There are also runtime-sensitive differences in:
- payment and manual payment handling
- support storage
- env/deploy wiring

## Safe
These areas are relatively safe to evolve and clean without affecting production runtime directly, as long as normal review discipline is preserved.

- canonical docs under `documentation/`
- `AGENTS.md`
- local smoke and contract tests:
  - `tests/test_dashboard_auth_session.py`
  - `tests/test_payment_finalization.py`
  - `tests/test_confirm_external_payment_record.py`
  - `tests/test_dashboard_api_v2_contract.py`
  - `tests/test_dashboard_api_v2_users_contract.py`
  - `tests/test_dashboard_api_v2_support_contract.py`
- small auth/security helper cleanup in `dashboard/security.py`
- safe local repo cleanup and `.gitignore` tightening

## Review-needed
These areas are not immediately runtime-critical, but should not be changed casually without checking intent and downstream assumptions.

- `README.md`
- `.env.example`
- older documentation layer files such as:
  - `documentation/README.md`
  - `documentation/supporting/dashboard.md`
  - `documentation/manifest.json`
- user-facing bot wording and flow-touching text:
  - `bot/utils/texts.py`
  - `bot/handlers/tariffs.py`
- supporting test/util layers such as `tests/test_access_reminders.py`

## Runtime-sensitive
These areas should not be cleaned up, moved, or rewritten without a separate plan and runtime-aware review.

### New admin contour
- `dashboard/ui/`

### Backend shaping and admin service layer
- `dashboard/v2_data.py`
- `dashboard/finance.py`
- `dashboard/main.py`
- `dashboard/models.py`
- `dashboard/services.py`

### Ops wiring and deployment surface
- `ops/env/amonora-dashboard-ui.env`
- `ops/nginx/amonora-dashboard.server.conf`
- `ops/systemd/amonora-dashboard-ui.service`
- `ops/access_reminders.py`
- `ops/server_watchdog.py`
- `ops/systemd/amonora-access-reminders.service`
- `ops/systemd/amonora-access-reminders.timer`
- `ops/systemd/amonora-server-watchdog.service`
- `ops/systemd/amonora-server-watchdog.timer`

### Payment / support persistence and flow-sensitive code
- `bot/manual_payments.py`
- `bot/handlers/tariffs.py`
- `support_bot/storage.py`

## Practical interpretation
- `safe`: can usually be improved freely
- `review-needed`: change only after a short intent review
- `runtime-sensitive`: do not clean, move, or simplify without a dedicated plan and runtime cross-check

## Recommended use
Use this document before:
- repo cleanup
- dashboard refactors
- `dashboard` vs `dashboard/ui` boundary changes
- payment/support flow changes
- ops or deploy rewiring
