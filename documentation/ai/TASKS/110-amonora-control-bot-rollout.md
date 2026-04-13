# 110 — Amonora Control Bot Rollout

## Context

System and administrative events were still mixed into `@amonora_support_bot`, which blurred the boundary between client support and internal operations:

- manual payment review lived inside the support bot;
- dashboard auth codes were delivered through the support bot;
- watchdog / node alerts used the same admin delivery seam;
- there was no single typed event log for internal notifications.

This task separates those flows by introducing `Amonora Control` as a dedicated internal Telegram bot and a centralized dispatcher/event-log layer.

## Scope

- add a new `control_bot` polling service;
- add `control_notification_events` as a central internal event log;
- route manual payment review, dashboard auth codes, node alerts, user lifecycle/access events and system errors into `Amonora Control`;
- remove payment review console from `support_bot`;
- keep `support_bot` only for client tickets, media, assignment and replies;
- add allowlist roles, command UI and payment review actions to `Amonora Control`;
- update runtime/systemd/docs/knowledge for the new bot.

## Constraints

- do not store real bot tokens in the repository;
- the token shown in chat is treated as compromised and must not be committed;
- `support_bot` media/ticket flows must remain intact;
- manual payment confirm/reject behavior must stay compatible with the existing payment finalization path;
- dashboard login-code verification flow must remain unchanged for the admin user.

## Acceptance Criteria

- `control_bot` exists as a separate package and polling service;
- internal notifications are written to `control_notification_events`;
- `/start`, `/status`, `/nodes`, `/payments`, `/users`, `/alerts`, `/login_codes`, `/help` work for allowed admins;
- support bot no longer exposes `/payments` or payment confirm/reject callbacks;
- dashboard auth request route points to `@amonora_control_bot`;
- manual payment notifications and review go to `Amonora Control`;
- docs and knowledge explicitly describe the new support/control split.

## Validation

- `./venv/bin/python -m unittest -q tests.test_control_dispatcher tests.test_control_queries tests.test_dashboard_auth_session`
- `./venv/bin/python -m unittest -q tests.test_payment_finalization tests.test_confirm_external_payment_record tests.test_support_storage tests.test_dashboard_support_attachment tests.test_dashboard_api_v2_support_contract`
- `./venv/bin/python -m unittest -q tests.test_access_reminders tests.test_dashboard_system_alerts tests.test_dashboard_api_v2_contract tests.test_bot_copy_updates tests.test_bot_devices_ui tests.test_device_region_change_guard`
- `python3 -m compileall control_bot support_bot dashboard bot backend ops tests documentation`
- `python3 -m json.tool documentation/manifest.json`
- `git diff --check`
