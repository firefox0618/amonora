# TASK 105 — Denmark Xray Core Node Rollout Result

## Result
Completed as an ops/runtime rollout.

The Denmark host `81.17.159.58` / `dk.amonoraconnect.com` is now running as a clean standalone `Xray core` node with:

- `VLESS`
- `Reality`
- `XHTTP`

The previous `x-ui` installation on that host was removed.

## What changed on Denmark
- hostname changed to `amonora-dk-1`;
- `x-ui` service was stopped, disabled, and removed from the host;
- standalone `xray` was installed from the official install path;
- `xray` now runs under `systemd` as `xray.service`;
- the active inbound is exposed on `443/tcp`;
- `ufw` now allows `22/tcp` and `443/tcp`;
- old panel-facing ports `2053/tcp` and `2096/tcp` were removed from the firewall rules.

## Validation evidence
- `xray run -test -config /usr/local/etc/xray/config.json` passed;
- `systemctl status xray` showed `active (running)`;
- `ss -tulpn` confirmed `*:443` is listening on the Denmark host;
- a temporary local client config on the Denmark host successfully connected through the new runtime;
- the self-test exit IP returned `81.17.159.58`, confirming real traffic went through the Denmark node.

## Backup and rollback evidence
- on-host pre-change backup directory:
  - `/root/task105-backup-20260320-183931`
- on-host runtime archive:
  - `/root/task105-dk-runtime-20260320-1845.tgz`
- local off-host copy:
  - `C:\\Ops\\Backups\\amonora\\vpn-dk\\2026-03-20_18-45\\task105-dk-runtime-20260320-1845.tgz`

## Important limitation
This task did **not** fully integrate Denmark into the current product provisioning flow.

Current bot/dashboard provisioning is still explicitly coupled to `XUIClient` / `3x-ui` assumptions across:

- bot device creation;
- payment-driven VPN sync;
- dashboard repair/re-sync actions;
- region metadata and VPN host maps.

So Denmark is now:

- operationally ready as a standalone clean Xray node;
- suitable for controlled testing and future rollout work;
- **not yet** a drop-in replacement for the current automated Germany/Estonia provisioning path.

## Estonia status
Estonia was not destroyed or migrated in this task.

Operationally, Denmark is now the cleaner test-ready node, while Estonia can remain available for reserve/testing work until a separate region-integration pass is completed.

## Follow-up
The next controlled step should be a separate implementation task that introduces a non-`x-ui` provisioner seam for Denmark before exposing it in:

- bot country selection;
- dashboard region-aware repair/device flows;
- overview/server health model;
- backup/status UI.
