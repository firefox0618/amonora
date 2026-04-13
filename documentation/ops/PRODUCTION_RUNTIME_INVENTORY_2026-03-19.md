# PRODUCTION RUNTIME INVENTORY

Date: 2026-03-19
Method: read-only SSH inventory against live servers
Status: completed

## Access path used

- practical working access from the current machine was confirmed via Windows OpenSSH, not WSL SSH;
- working backend entry command pattern:
  - `ssh -i C:\Users\Skyfal\.ssh\id_ed25519 root@46.21.81.186`
- WSL-side direct SSH reachability was inconsistent during earlier attempts and should not be treated as the canonical access path.

## Server inventory

### Amonora Core / backend

- hostname: `hiplet-78194`
- public IP: `46.21.81.186`
- role:
  - core/backend
  - PostgreSQL
  - main Telegram bot
  - support bot
  - control bot
  - dashboard backend/API
  - panel UI
  - landing
  - nginx
- confirmed active services:
  - `amonora-bot.service`
  - `amonora-support-bot.service`
  - `amonora-control-bot.service`
  - `amonora-dashboard.service`
  - `amonora-dashboard-ui.service`
  - `amonora-landing.service`
  - `amonora-xui-tunnel.service`
  - `amonora-xui-tunnel-ee.service`
  - `nginx.service`
  - `postgresql@16-main.service`
  - `ssh.service`
- confirmed listening ports:
  - `0.0.0.0:80` -> `nginx`
  - `0.0.0.0:443` -> `nginx`
  - `0.0.0.0:22` -> `sshd`
  - `127.0.0.1:3001` -> `dashboard/ui`
  - `127.0.0.1:8088` -> `dashboard`
  - `127.0.0.1:8090` -> `landing`
  - `127.0.0.1:5432` -> `PostgreSQL`
  - `127.0.0.1:12053` -> SSH tunnel to primary VPN XUI
  - `127.0.0.1:12054` -> SSH tunnel to Estonia VPN XUI
- confirmed runtime directories:
  - repo/runtime root: `/opt/amonora_bot`
  - `dashboard/ui`: `/opt/amonora_bot/dashboard/ui`
- confirmed env paths:
  - shared Python services: `/opt/amonora_bot/.env`
  - dashboard v2: `/etc/amonora-dashboard-ui.env`
- confirmed unit execution model:
  - `amonora-bot.service` -> `/opt/amonora_bot/venv/bin/python -m bot.main`
  - `amonora-support-bot.service` -> `/opt/amonora_bot/venv/bin/python -m support_bot.main`
  - `amonora-control-bot.service` -> `/opt/amonora_bot/venv/bin/python -m control_bot.main`
  - `amonora-dashboard.service` -> `/opt/amonora_bot/venv/bin/uvicorn dashboard.main:app --host 127.0.0.1 --port 8088`
  - `amonora-landing.service` -> `/opt/amonora_bot/venv/bin/python -m landing.main`
  - `amonora-dashboard-ui.service` -> `node ... next start -H 127.0.0.1 -p 3001`
- confirmed nginx layout:
  - enabled site: `/etc/nginx/sites-enabled/amonora-dashboard`
  - source config: `/etc/nginx/sites-available/amonora-dashboard`
- confirmed database runtime:
  - PostgreSQL cluster: `16/main`
  - data path: `/var/lib/postgresql/16/main`
  - DB listener: `127.0.0.1:5432`
  - confirmed databases:
    - `amonora_db`
    - `postgres`
    - `template0`
    - `template1`
- confirmed timers:
  - `amonora-server-watchdog.timer`

### Germany VPN node

- hostname: `amonora-vpn-de`
- public IP: `213.108.20.34`
- role:
  - primary user-facing VPN node
  - `3x-ui` / `Xray`
- confirmed active runtime:
  - `docker.service`
  - `containerd.service`
  - `ssh.service`
  - `amonora-xui-shield.service`
  - `/app/x-ui`
  - `bin/xray-linux-amd64 -c bin/config.json`
- confirmed listening ports:
  - `*:443` -> Xray
  - `*:8443` -> Xray
  - `*:2053` -> `x-ui`
  - `*:2096` -> `x-ui`
  - `*:22` -> `sshd`
  - `127.0.0.1:11111` -> Xray local port
  - `127.0.0.1:62789` -> Xray local port
- confirmed runtime paths:
  - `/opt/3x-ui`
  - `/opt/3x-ui/db/x-ui.db`
  - `/opt/3x-ui/backups`
- confirmed service files:
  - `/etc/systemd/system/amonora-xui-shield.service`

### Estonia VPN node

- hostname: `hiplet-77252`
- public IP: `185.88.37.71`
- role:
  - secondary / reserve VPN node
  - `3x-ui` / `Xray`
- confirmed active runtime:
  - `docker.service`
  - `containerd.service`
  - `ssh.service`
  - `amonora-xui-shield.service`
  - `/app/x-ui`
  - `bin/xray-linux-amd64 -c bin/config.json`
- confirmed listening ports:
  - `*:443` -> Xray
  - `*:8443` -> Xray
  - `*:2053` -> `x-ui`
  - `*:2096` -> `x-ui`
  - `*:22` -> `sshd`
  - `127.0.0.1:11111` -> Xray local port
  - `127.0.0.1:62789` -> Xray local port
- confirmed runtime paths:
  - `/opt/3x-ui`
  - `/opt/3x-ui/db/x-ui.db`
  - `/opt/3x-ui/backups`
- confirmed service files:
  - `amonora-xui-shield.service`

## Confirmed topology

- production currently runs on three VPS:
  - one core/backend server
  - one Germany VPN node
  - one Estonia VPN node
- backend and VPN are split physically;
- backend integrates with node panels through local tunnel ports:
  - `127.0.0.1:12053`
  - `127.0.0.1:12054`
- public web entry is terminated by `nginx` on the core server;
- `dashboard/ui` is a separate Next.js process behind `nginx`;
- `dashboard` remains the active backend/API/admin service on `127.0.0.1:8088`.

## Confirmed mismatches vs earlier local assumptions

- `dashboard/ui` env file is confirmed at `/etc/amonora-dashboard-ui.env`, not under `/opt/amonora_bot/ops/env/...` at runtime;
- production unit names are confirmed and should be treated as canonical:
  - `amonora-bot.service`
  - `amonora-support-bot.service`
  - `amonora-dashboard.service`
  - `amonora-dashboard-ui.service`
  - `amonora-landing.service`
- PostgreSQL is confirmed as local-only on the core host via `127.0.0.1:5432`;
- the VPN nodes do expose `2053` and `2096` listeners locally on the hosts, even though backend integration is designed around tunnel access;
- Estonia still has a live `51820/udp` legacy listener.

## Unresolved or still worth verifying

- exact backup automation for application/database dumps is still not fully mapped from live runtime alone;
- retention rules for `/opt/3x-ui/backups` and any Postgres dump rotation still need a dedicated backup pass;
- the earlier live note about `amonora-xui-ee-tunnel.service` should be reconciled with the currently confirmed active unit naming on the backend host;
- nginx config contents should be kept in sync with the repo copy in `ops/nginx/`.

## Safe follow-up tasks

- complete runtime/runbook reconciliation pass;
- do a dedicated backup verification task;
- do not remove legacy VPN or admin paths until backup and migration coverage are explicitly checked.
