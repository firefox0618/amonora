# TASK 129 RESULT — Bot split-routing pack delivery

## Outcome
The bot now exposes a safe additive split-routing flow: users keep receiving the same VPN keys as before, and can additionally download a client-matched JSON pack that routes Russian destinations directly and foreign traffic through VPN.

## What changed
- added a shared routing builder that emits Xray-compatible split/full routing packs with `domainStrategy = IPIfNonMatch`;
- added a `🧭 Маршруты РФ` button on the device surfaces so users can download the split-routing pack without leaving the active bot flow;
- aligned the official `v2rayNG`, `Nekoray`, and `Streisand` JSON artifacts with the same runtime routing policy;
- updated user-facing guidance and feature docs so the split-routing flow is documented in the same terms users see in the bot;
- added focused tests that verify the runtime builder, OS-to-client mapping, documented JSON artifacts, and the new bot button surface.

## Validation completed
- `./venv/bin/python -m py_compile bot/utils/routing.py bot/handlers/devices.py bot/keyboards/devices.py bot/utils/texts.py`
- `./venv/bin/python -m unittest tests.test_client_routing_packs tests.test_bot_copy_updates tests.test_bot_modes tests.test_bot_devices_ui`
- `python3 -m json.tool documentation/vpn/client-packs/v2rayng-split-tunnel.json`
- `python3 -m json.tool documentation/vpn/client-packs/nekoray-split-tunnel.json`
- `python3 -m json.tool documentation/vpn/client-packs/streisand-split-tunnel.json`
- `python3 -m json.tool documentation/vpn/client-packs/v2rayng-full-tunnel.json`
- `python3 -m json.tool documentation/vpn/client-packs/nekoray-full-tunnel.json`
- `python3 -m json.tool documentation/vpn/client-packs/streisand-full-tunnel.json`

## Residual risks
- `vless://` and `trojan://` URI keys still cannot embed routing rules, so the split-routing policy remains a separate importable client pack by design;
- the new flow is additive and does not auto-rewrite legacy client configs, which preserves stability for existing active users but still requires explicit user import where split routing is needed.
