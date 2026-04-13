# TASK 142 — Estonia test-node key activation MVP

## Status
Completed

## Goal
Use the existing Estonia `EE` test node as a controlled VPN activation pilot and add a server-side activation seam that binds a VPN key/device secret to a reported device fingerprint.

## Scope
- `backend/core/models.py`
- `bot/db.py`
- `landing/main.py`
- focused landing tests
- task/state/docs updates

## Constraints
- do not replace or repurpose the active Germany/Denmark user-facing routes;
- treat Estonia as an existing `3x-ui`-backed test node, not a fresh production region;
- keep validation on the server side;
- avoid storing raw fingerprint text when a stable hash is enough.

## Acceptance criteria
- the repo exposes a hidden HTTP seam for app-side activation requests;
- the server validates the VPN key against an existing stored VPN client;
- the MVP only accepts Estonia-scoped VPN clients;
- repeated activation from the same fingerprint updates the same record;
- new fingerprints are limited by the configured device cap;
- focused tests cover invalid key, unsupported region, and successful Estonia activation.
