# TASK 128 — Bot split-routing pack delivery

## Status
Completed

## Goal
Add a safe client-side split-routing layer so Russian destinations stay direct while foreign traffic goes through VPN, without changing the existing provisioning and key-delivery flow.

## Why
- current device delivery sends URI keys, but URI-only links cannot carry Xray routing rules;
- the project already has official client-pack artifacts, but the bot does not deliver them directly to users from the active device flow;
- the desired product behavior is split tunneling for RU resources, not server-side access changes.

## Scope
- introduce a shared builder for official routing packs and Xray-compatible routing rules;
- add a device-surface button that sends a split-routing JSON pack matched to the device OS/client family;
- update official client-pack JSON artifacts and user-facing copy/docs;
- add focused tests for routing packs and the new bot surface.

## Out of scope
- changing node-side Xray routing for user traffic;
- rewriting the current `vless://` / `trojan://` key flow;
- forcing split routing on legacy users automatically.

## Constraints
- existing key/QR/device flows must keep working unchanged;
- split routing must be additive and reversible;
- Russian direct routing should stay a client-side pack/instruction concern;
- avoid introducing technical overload into the default happy path.

## Acceptance criteria
- a shared routing builder emits Xray-compatible rules with RU direct, foreign proxy, and bittorrent blocked;
- device UI exposes a safe path to download the routing pack;
- official JSON client packs reflect the same split/full policy;
- user guidance mentions the new routing pack flow;
- targeted tests cover builder output and the new bot button surface.

## Validation
- `./venv/bin/python -m unittest tests.test_client_routing_packs tests.test_bot_copy_updates`
- `./venv/bin/python -m unittest tests.test_bot_modes tests.test_bot_devices_ui`
- `python3 -m json.tool documentation/vpn/client-packs/v2rayng-split-tunnel.json`
- `python3 -m json.tool documentation/vpn/client-packs/nekoray-split-tunnel.json`
- `python3 -m json.tool documentation/vpn/client-packs/streisand-split-tunnel.json`
