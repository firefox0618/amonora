# TASK 156 — n8n channel workflows runtime repair

## Status
Completed

## Goal
Restore the production `n8n` runtime so the repo-managed channel-MVP schedules are actually present and active on the core host.

## Why
`n8n` itself was running, but the live instance contained only the experimental `amonora_daily_news_*` workflows.  
The core channel-MVP workflows from `ops/n8n/workflows/*` were missing, so:
- scheduled `publish_approved_channel_posts` could not fire at all;
- scheduled `generate_due_channel_drafts` and `remind_missing_channel_content` were also absent;
- manual `POST /dashboard/api/internal/channel/publish` still worked, but correctly returned `processed_count = 0` because there was no scheduler behind it and no due items in PostgreSQL.

## Scope
- verify live `n8n` runtime state on the core host;
- back up current `n8n` workflow state and SQLite DB;
- import repo-managed channel-MVP workflows into production `n8n`;
- activate the imported workflows and restart `amonora-n8n.service`;
- record the remaining daily-news credentials issue separately instead of mixing it with the core publish path.

## Acceptance criteria
- production `n8n` contains `generate_due_channel_drafts`, `publish_approved_channel_posts`, and `remind_missing_channel_content`;
- all three are marked active in the live `n8n` database;
- `amonora-n8n.service` is running after the repair;
- internal channel publish endpoint still responds successfully.
