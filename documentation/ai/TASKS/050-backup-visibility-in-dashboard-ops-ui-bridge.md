# TASK 050 — Backup visibility in dashboard (ops → UI bridge)

## Status
Completed

## Goal
Expose backup health (already implemented locally) into the dashboard so backup state is not only known via scripts, but visible in the product.

## Outcome

Backup visibility in overview is now more explicit:
- overall freshness still exists
- stale rule is shown in UI
- per-source backup rows now surface `core-pg`, `vpn-de`, and `vpn-ee` when available

## Scope kept intentionally narrow

Included:
- lightweight per-source visibility based on existing local filesystem state
- no orchestration changes
- no remote integrations

Not included:
- S3 visibility
- restore automation
- server-side agents
