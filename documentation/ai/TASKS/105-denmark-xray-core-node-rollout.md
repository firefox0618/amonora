# TASK 105 — Denmark Xray Core Node Rollout

## Status
Completed

## Goal
Bring up a new Denmark VPN node at `dk.amonoraconnect.com` as a clean standalone `Xray core` server with `VLESS + Reality + XHTTP`, while moving away from `x-ui` on that host.

## Why
The current Germany/Estonia product flow is tightly coupled to `3x-ui` control-plane assumptions.

The Denmark node is intended to become a cleaner runtime baseline:

- no `x-ui` panel on the host;
- direct `Xray core` runtime;
- modern `VLESS + Reality + XHTTP` transport;
- explicit backup and rollback evidence before wider integration.

## Scope
- verify access to the Denmark host;
- make a pre-change backup on the Denmark host;
- remove `x-ui` from that host;
- install standalone `Xray core`;
- configure `VLESS + Reality + XHTTP`;
- validate the node with a real local self-test from the Denmark host;
- capture backup/checkpoint evidence.

## Out of scope
- automatic backend provisioning for Denmark;
- replacing the current `XUIClient` provisioning seam in bot/dashboard;
- switching production user traffic to Denmark by default;
- removing Estonia from backend/runtime code paths;
- shipping Denmark into end-user country selection.

## Constraints
- existing production Germany/Estonia flows must not be broken;
- no blind migration of current users;
- changes on Denmark must be reversible from a pre-change backup;
- docs must clearly state that Denmark is operationally ready but not yet product-integrated.

## Validation
- `x-ui` is removed from Denmark;
- `xray` is installed and enabled via `systemd`;
- `xray run -test -config ...` passes;
- port `443/tcp` is listening on the Denmark host;
- local self-test through a temporary client config returns the Denmark public IP;
- backup artifacts exist both on-host and in the local off-host backup location.
