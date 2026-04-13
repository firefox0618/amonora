# TASK 106 — Denmark Provider Integration

## Status
In progress

## Goal
Integrate the standalone Denmark `Xray core` node into the existing Amonora Connect product flow without forcing it into the `3x-ui` control plane.

## Why
Task `105` made Denmark operationally ready as a clean `VLESS + Reality + XHTTP` node, but the active product flow still assumed that every VLESS region is backed by `XUIClient`.

This task introduces a provider-based seam so that:

- `de` and `ee` stay on the current `3x-ui` path;
- `dk` is handled through a standalone `Xray core` provisioner;
- current Germany/Estonia users are not broken during the transition.

## Scope
- add a provider-aware VLESS provisioning seam for bot and dashboard flows;
- keep `XUIClient` as the low-level implementation for `de` / `ee`;
- add an `XrayCoreProvisioner` for `dk`;
- split region metadata from panel metadata;
- hide Estonia from user-facing region selection;
- keep Denmark gated to admin/test usage instead of broad user rollout;
- make payment sync and repair flows provider-aware for VLESS;
- make dashboard server/watchdog surfaces provider-aware enough for Denmark;
- update env template and operational docs.

## Out of scope
- broad user rollout of Denmark to all clients;
- migrating existing Germany/Estonia devices to Denmark;
- reintroducing `x-ui` on Denmark;
- changing Trojan or WireGuard provisioning away from `3x-ui`.

## Constraints
- Germany remains the primary live user region;
- Estonia remains reserve/testing infrastructure;
- Denmark must stay on standalone `Xray core`;
- the new seam must not silently fallback to Germany when `dk` has no panel URL;
- repair source / outcome normalization stays shared across providers.

## Validation
- local Python regression set stays green for region, payment, dashboard repair, and v2 contract checks;
- Germany create/sync/delete VLESS path still resolves through `XUIClient`;
- Denmark VLESS path resolves through the new `XrayCoreProvisioner`;
- dashboard server/watchdog surfaces no longer assume Denmark has `3x-ui`;
- production core host can SSH into Denmark using the dashboard metrics key;
- a controlled Denmark test user can receive a working VLESS config through the product flow.
