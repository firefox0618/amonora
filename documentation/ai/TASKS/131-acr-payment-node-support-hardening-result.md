# Task 131 Result — Safe ACR Hardening for Payments, Support, and Nodes

## Outcome

The second safe ACR hardening pass was implemented without broad refactors:

- dashboard-confirmed non-manual payments now use the shared `finalize_subscription_payment(...)` orchestration instead of a direct `extend_subscription_for_user(...)` shortcut;
- `support_bot.storage.get_ticket_counts(...)` now computes counts through SQL aggregates after the normal prune pass instead of materializing the whole queue;
- control-bot node detail now exposes `Обновить статус` and routes both `refresh` and legacy `resync` callbacks through the safe refresh/health-check path;
- server migration now skips devices without explicit source-node binding, marks the result as requiring manual review, and does not auto-switch the source node to `maintenance` on partial migration.

## Files changed

- `dashboard/services.py`
- `support_bot/storage.py`
- `control_bot/queries.py`
- `control_bot/router.py`
- `tests/test_dashboard_acr_second_pass.py`
- `tests/test_support_storage_counts.py`
- `tests/test_control_queries.py`
- `documentation/FEATURES.md`
- `documentation/ai/STATE.md`

## Validation

- targeted tests: `27` tests `OK`
- extended regression suite: `88` tests `OK`
- `py_compile` on changed Python files: `OK`

## Notes

- this pass reduces operator-facing false-success paths and unsafe migration semantics, but it does not fully turn the entire payment/access/node chain into one DB+node transaction;
- production deploy was not part of the implementation result itself and still depends on verified server access.
