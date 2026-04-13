# 111 — Referral Balance Backfill, Panel UI Unification, and WireGuard Cleanup Result

## Summary

Задача выполнена.

В результате:

- пользовательская кнопка переименована в `🎁 Реферальная система`;
- referral migration/backfill теперь корректно доначисляет рубли старым приглашённым пользователям;
- support bot принимает только `text`, `photo`, `video`, `audio`, а остальные media types отклоняет;
- новый admin frontend окончательно перенесён из `dashboard_v2` в `dashboard/ui`;
- production service renamed to `amonora-dashboard-ui.service`;
- user-facing и актуальные doc/runtime traces `WireGuard` убраны;
- legacy `wireguard` inbound `id=2` на Estonia удалён через `3x-ui` API.

## Files changed

### Product code

- `bot/db.py`
- `bot/handlers/devices.py`
- `bot/keyboards/devices.py`
- `bot/keyboards/main_menu.py`
- `bot/payment_flow.py`
- `bot/utils/regions.py`
- `bot/utils/texts.py`
- `bot/vpn_api.py`
- `support_bot/router.py`
- `dashboard/services.py`
- `ops/vpn_regions.py`
- `bot/config.py`

### Admin UI / ops

- `dashboard/ui/*`
- `ops/systemd/amonora-dashboard-ui.service`
- `ops/env/amonora-dashboard-ui.env`

### Documentation

- `README.md`
- `documentation/PROJECT_OVERVIEW.md`
- `documentation/ARCHITECTURE.md`
- `documentation/DOMAIN.md`
- `documentation/FEATURES.md`
- `documentation/RUNBOOK.md`
- `documentation/manifest.json`
- `documentation/supporting/dashboard.md`
- `documentation/supporting/panel-ui-deep-dive.md`
- `documentation/supporting/user-guide.md`
- `documentation/supporting/bot-flow.md`
- `documentation/supporting/support-bot.md`
- `documentation/supporting/amonora-control-bot.md`
- related ops / strategy / product docs touched by the cleanup

### Tests

- `tests/test_bot_copy_updates.py`
- `tests/test_referral_balance.py`
- `tests/test_support_router_policy.py`

## Validation

### Local

- `./venv/bin/python -m unittest -q tests.test_referral_balance tests.test_referral_ui tests.test_bot_copy_updates tests.test_support_router_policy tests.test_support_storage tests.test_dashboard_support_attachment tests.test_payment_finalization tests.test_confirm_external_payment_record tests.test_dashboard_api_v2_support_contract tests.test_dashboard_api_v2_contract tests.test_device_region_change_guard`
- result: `Ran 41 tests / OK`
- `python3 -m compileall bot support_bot dashboard control_bot ops documentation tests`
- `git diff --check`

### Production

- backup root:
  - `/opt/amonora_bot_backup/referral-panel-cleanup-20260322-052624`
- `dashboard/ui` synced to `/opt/amonora_bot/dashboard/ui`
- old `/opt/amonora_bot/dashboard_v2` removed
- new UI service:
  - `amonora-dashboard-ui.service` -> `active`
- old UI service:
  - `amonora-dashboard-v2.service` -> `not-found`
- build:
  - `npm ci`
  - `npm run build`
  - completed successfully on core host
- referral reconcile:
  - `{'users_scanned': 53, 'users_credited': 4, 'credited_rub': 250}`
- specific user verification:
  - `548589949|50|1|1`
- Estonia inbound verification after cleanup:
  - only `vless:443` and `trojan:8443` remain
  - `wireguard:51820` inbound removed

## Risks / follow-up

- SSH to the core host was intermittently unstable during rollout; runtime was updated through short retry-based commands instead of one long session.
- `dashboard` backend remains a separate Python layer by design; only the duplicate top-level frontend folder was removed.
- local `npm run typecheck` from this WSL environment still hits the known UNC/Windows issue, but production `npm run build` passed on the server.
