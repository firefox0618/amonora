## Task 128 Result

### Done

- support bot admin panel now renders only the latest 5 tickets per filter and tells the operator when more items remain in the queue;
- support ticket loading gained SQL-side filtering and optional limit support instead of always loading and slicing in Python;
- `@amonora_bot` now activates first-time trial access immediately on `/start` without blocking the user on channel membership;
- dashboard users payload/detail now expose a cached channel-subscription status for `@amonora_vpn`;
- channel-subscription checks are bounded by concurrency, cached, and degrade to `Не проверено` instead of failing the whole users page;
- the control-bot support queue was aligned to the same short operational slice;
- `bot.utils.access.utcnow()` now uses a timezone-aware source while preserving the existing naive-UTC contract.

### Validation

- `./venv/bin/python -m unittest tests.test_support_router_policy tests.test_bot_start_trial tests.test_dashboard_channel_subscription_status tests.test_control_queries tests.test_control_router tests.test_control_dispatcher tests.test_dashboard_auth_session tests.test_dashboard_acr_fixes tests.test_dashboard_vpn_repair tests.test_payment_finalization tests.test_confirm_external_payment_record tests.test_dashboard_api_v2_settings_contract tests.test_dashboard_api_v2_role_access tests.test_dashboard_api_v2_support_contract tests.test_dashboard_api_v2_users_contract`
- `./venv/bin/python -m py_compile support_bot/router.py support_bot/storage.py bot/handlers/start.py dashboard/services.py dashboard/v2_data.py control_bot/queries.py`
- frontend typecheck via Windows Node path against `dashboard/ui/tsconfig.json`

### Follow-up

- the users payload still builds from broad user/client/payment scans and should later move toward narrower server-side pagination or pre-aggregates if the real user count grows materially;
- live node/server runtime verification still requires production access and was not performed in this local change set.
