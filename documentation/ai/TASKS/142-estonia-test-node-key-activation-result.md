# TASK 142 — Estonia test-node key activation MVP result

## Outcome
The existing Estonia `EE` node remains the live test-only VPN surface, and the core host now exposes a hidden server-side activation seam for Estonia VPN keys at `POST /vpn/activate`.

## What changed
- added `VpnClientActivation` storage in `backend/core/models.py`;
- added `bot.db` helpers to resolve a VPN client by secret and register/update device activations with a per-key device cap;
- added `landing.main` endpoint `POST /vpn/activate` that:
  - accepts `key + device_fingerprint + optional device metadata`;
  - hashes the fingerprint instead of storing it raw;
  - only accepts VPN clients whose stored region is `EE`;
  - validates active access before activation;
  - updates the same row on repeat activation from the same fingerprint;
  - rejects extra fingerprints once the configured device cap is reached;
  - applies a small in-process rate limit.
- added focused landing tests for invalid key, unsupported region, and successful Estonia activation.

## Validation
- local:
  - `./venv/bin/python -m py_compile backend/core/models.py bot/db.py landing/main.py tests/test_landing_vpn_activation.py`
  - `./venv/bin/python -m unittest tests.test_landing_vpn_activation`
- production:
  - `AUTO_APPLY_SCHEMA=1` confirmed on core host
  - schema apply executed successfully
  - `amonora-landing.service` restarted successfully
  - smoke check:
    - `POST http://127.0.0.1:8090/vpn/activate` with an unknown key returns `404 {"ok":false,"status":"invalid_key"}`
  - Estonia node `185.88.37.71` still showed active `3x-ui` runtime with listeners on `443/8443` during the rollout window

## Constraints kept
- no change to normal Germany/Denmark user-facing routing;
- no promotion of Estonia into the normal public region picker;
- no raw fingerprint persistence;
- no new bot/dashboard runtime restart beyond `amonora-landing.service`.
