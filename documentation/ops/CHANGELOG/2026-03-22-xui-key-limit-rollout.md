Date: 2026-03-22
Server: Core / backend (`46.21.81.186`)
Component: Bot / x-ui key delivery / access sync
Change:
- enforced `limitIp = 1` for newly created `x-ui` VLESS and Trojan clients
- preserved the same limit during VLESS/Trojan sync paths
- re-applied the limit before key and QR reissue for existing `x-ui` devices
- prepared a one-off post-deploy sync pass so existing `x-ui` devices do not stay on historical unlimited limits
Reason:
- device-count limits were weaker than expected because one issued key could still be reused across multiple devices
- the product needs one key to stop behaving like an unlimited shared credential on `x-ui`-backed regions
Risk: medium
Checks:
- `./venv/bin/python -m unittest tests.test_xui_key_limit`
- `./venv/bin/python -m unittest tests.test_bot_copy_updates tests.test_bot_devices_ui`
- `./venv/bin/python -m py_compile bot/vpn_api.py bot/handlers/devices.py tests/test_xui_key_limit.py`
- `git diff --check -- bot/vpn_api.py bot/handlers/devices.py tests/test_xui_key_limit.py documentation/DOMAIN.md documentation/FEATURES.md documentation/ai/STATE.md documentation/ai/TASKS/116-xui-key-reuse-limit-hardening.md documentation/ops/CHANGELOG/2026-03-22-xui-key-limit-rollout.md`
- post-deploy on core host:
  - `./venv/bin/python -m unittest tests.test_xui_key_limit`
  - `./venv/bin/python -m py_compile bot/vpn_api.py bot/handlers/devices.py tests/test_xui_key_limit.py`
  - one-off x-ui device sync result: `updated=43`, `skipped=8`, `error_count=0`
  - `systemctl is-active amonora-bot.service amonora-dashboard.service` -> both `active`
Rollback:
- restore previous versions of `bot/vpn_api.py`, `bot/handlers/devices.py`, tests, and docs
- sync restored files back to `/opt/amonora_bot`
- restart `amonora-bot.service`
- run a follow-up device access sync if rollback touched already-updated panel clients
Status: OK
