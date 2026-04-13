# TASK 005 RESULT — Production runtime inventory

## Status
Completed

## Outcome

Production runtime inventory was completed in read-only mode against live servers.

## What was confirmed

- working access path exists through Windows OpenSSH with the Windows SSH key;
- the production topology is confirmed as:
  - one core/backend server
  - one Germany VPN node
  - one Estonia VPN node
- live unit names, ports, runtime directories and env file paths were confirmed from real servers;
- no committed secrets were introduced during the inventory.

## What was attempted

- checked local SSH notes and key material;
- confirmed the working access path through Windows `ssh`;
- ran read-only live inventory commands on:
  - backend/core `46.21.81.186`
  - Germany node `213.108.20.34`
  - Estonia node `185.88.37.71`
- collected service, port, runtime path, postgres and VPN-node facts from live systems.

## What was observed

- the practical working path from this machine is Windows OpenSSH, not WSL SSH;
- backend host runs the active core stack:
  - bots
  - dashboard backend
  - dashboard v2
  - landing
  - nginx
  - PostgreSQL
  - XUI SSH tunnels
- VPN nodes run `3x-ui` and `Xray` and expose live listeners on `443`, `8443`, `2053`, and `2096`;
- Estonia still has a legacy `51820/udp` listener.

## Main outputs

- canonical runtime inventory doc:
  - `documentation/ops/PRODUCTION_RUNTIME_INVENTORY_2026-03-19.md`
- confirmed runbook inputs:
  - production unit names
  - confirmed ports
  - confirmed runtime and env paths
  - confirmed database location
- mismatch list between repo assumptions and live runtime

## Follow-up still needed

- dedicated backup verification pass;
- reconcile any older notes that still mention alternate tunnel unit naming;
- keep `RUNBOOK.md` aligned with the live runtime findings.
