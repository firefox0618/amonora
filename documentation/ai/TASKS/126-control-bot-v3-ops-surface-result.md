## Task 126 Result

### Done

- `control_bot` was extended into a real operational Telegram surface:
  - new shell/navigation for `Dashboard`, `Problems`, `Support`, `Notifications`, `User`;
  - `/user` lookup and user focus cards with `sync / deep repair / trial / extend / block / clear-access`;
  - support screens and actions using the same backend/support seams as the panel;
  - node focus cards with `health check / restart / maintenance / resync(refresh)`;
  - richer payment focus with linked user context and `open user`;
  - 5-minute dashboard login codes and a richer `login_codes` screen.

- notification handling was updated:
  - control notification preferences now use `payments / users / support / nodes / security / system`;
  - role-aware defaults were added;
  - mandatory categories by role are now enforced and shown as locked in the bot UI;
  - legacy categories are mapped into the new preference buckets.

- support now emits safe control events for new/reopened tickets, and support-close paths try to resolve the open support incident signal without breaking ticket closure if the control-event layer is unavailable.

### Files changed

- `control_bot/access.py`
- `control_bot/dispatcher.py`
- `control_bot/keyboards.py`
- `control_bot/main.py`
- `control_bot/queries.py`
- `control_bot/router.py`
- `control_bot/storage.py`
- `support_bot/router.py`
- `dashboard/main.py`
- `dashboard/services.py`
- `tests/test_control_queries.py`
- `documentation/FEATURES.md`
- `documentation/supporting/amonora-control-bot.md`
- `documentation/ai/STATE.md`

### Validation

- `./venv/bin/python -m py_compile control_bot/access.py control_bot/dispatcher.py control_bot/keyboards.py control_bot/main.py control_bot/queries.py control_bot/router.py support_bot/router.py dashboard/main.py dashboard/services.py`
- `./venv/bin/python -m unittest tests.test_control_queries tests.test_control_router tests.test_control_dispatcher tests.test_dashboard_auth_session tests.test_dashboard_acr_fixes tests.test_dashboard_vpn_repair tests.test_payment_finalization tests.test_confirm_external_payment_record tests.test_dashboard_api_v2_settings_contract tests.test_dashboard_api_v2_role_access tests.test_dashboard_api_v2_support_contract`

### Follow-up

- `support` delivery still physically goes through `@amonora_support_bot`; `@amonora_control_bot` is now an operator surface over that same ticket state, not a second support transport.
- numeric free-form extension days and deeper per-device actions are still stronger in the web panel than in Telegram.
