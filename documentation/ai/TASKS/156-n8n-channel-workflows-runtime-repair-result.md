# TASK 156 — n8n channel workflows runtime repair result

## Status
Completed

## What changed
- production `n8n` was audited and found to contain only `amonora_daily_news_generate` and `amonora_daily_news_approval`;
- the repo-managed core channel workflows were missing from the live instance, so they could not schedule generate/publish/reminder actions at all;
- imported `generate_due_channel_drafts`, `publish_approved_channel_posts`, and `remind_missing_channel_content` from `ops/n8n/workflows/*` into the core host `n8n`;
- activated those three workflows directly in the live `n8n` SQLite state and restarted `amonora-n8n.service`;
- confirmed that the internal publish hook still returns `200`, and at the moment it reports `processed_count = 0` because the `channel_content_items` table is currently empty rather than because the runtime is broken.

## Runtime evidence
- backup: `/root/codex-backups/task156-n8n-channel-workflows-20260403-005432`
- imported workflow IDs:
  - `XlBb3x8xIKZxcl3b` — `generate_due_channel_drafts`
  - `IGnpcAkizJ9A2Kc8` — `publish_approved_channel_posts`
  - `BG3luCUgxqTKUroq` — `remind_missing_channel_content`
- live active flags after repair: all three set to `1`
- `amonora-n8n.service` restarted successfully at `2026-04-02 19:57:57 UTC`

## Remaining note
- experimental `amonora_daily_news_*` workflows are a separate path and still show a credentials-related activation problem in `n8n` logs (`Node does not have any credentials set` for the approval workflow). That issue does not block the restored core channel-MVP schedules.

## Validation
- `systemctl status amonora-n8n.service`
- `n8n list:workflow`
- direct `POST http://127.0.0.1:8088/dashboard/api/internal/channel/publish`
