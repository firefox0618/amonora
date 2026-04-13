# TASK 005 — Production runtime inventory

## Status
Completed

## Goal
Create a read-only inventory of the production/runtime environment so local documentation can be verified against real deployed infrastructure.

## Why
The project now has a strong local documentation layer, but repository truth and runtime truth may differ.
Before making operational changes, cleanup decisions, or deployment assumptions, the real production environment must be mapped and confirmed.

## Context
Relevant docs:
- `documentation/RUNBOOK.md`
- `documentation/REPO_RULES.md`
- `documentation/PRIVATE_ACCESS.template.md`
- `documentation/ops/CURRENT_STATE_2026-03-19.md`
- `documentation/ops/DEPLOY_RULES.md`
- `documentation/ops/ROLLBACK.md`
- `documentation/vpn/VPN_CONFIG_STRATEGY.md`
- `documentation/ai/STATE.md`

Relevant sources:
- production servers
- VPS/provider panels
- systemd services
- nginx config
- environment files
- PostgreSQL instance(s)
- VPN/Xray/3x-ui nodes
- backup locations

## Current behavior
Local documentation describes the system based on repository structure and partial operational knowledge, but some runtime details may still be inferred rather than confirmed.

## Desired behavior
There should be a read-only inventory document that confirms:
- which servers exist
- the role of each server
- which services run where
- which ports are actually used
- which runtime paths are actually used
- where production data lives
- where backups live
- which VPN nodes are active
- what still requires verification

## Scope
- inventory servers and their roles
- inventory active services and systemd units
- inventory nginx sites / reverse proxy layout
- inventory runtime directories and env file paths
- inventory PostgreSQL location and role
- inventory active VPN/Xray/3x-ui nodes
- inventory backup locations and backup method
- capture confirmed facts and unresolved questions

## Out of scope
- changing server config
- restarting services
- deploying code
- editing nginx/systemd/env files
- changing database schema
- deleting old configs or data
- rotating secrets

## Constraints
- read-only only
- no cleanup during inventory
- no assumptions presented as confirmed facts
- sensitive values must not be committed into git-tracked docs
- use `PRIVATE_ACCESS.md` locally for sensitive host/access notes if needed

## Risks
- confusing staging/test hosts with production hosts
- documenting incomplete runtime information as final truth
- exposing secrets while collecting notes
- missing hidden dependencies between services

## Acceptance criteria
- inventory document exists
- each known server has a role description
- active services are listed per server
- key ports and runtime paths are noted
- primary data locations are identified
- backup locations/methods are identified
- active VPN nodes are identified
- unresolved items are clearly marked as needing verification

## Validation
Manual checks:
- compare server inventory with actual SSH/systemd/nginx/runtime output
- verify service names and ports from live systems
- verify database and backup locations from real environment
- confirm that no secrets were added to tracked documentation

## Deliverables
- production runtime inventory document
- updated notes for `RUNBOOK.md`
- list of mismatches between local docs and runtime reality
- list of follow-up operational verification tasks
