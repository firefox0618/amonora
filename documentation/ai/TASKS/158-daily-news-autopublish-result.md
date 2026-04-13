## Result

- added dashboard internal autopublish seam for `daily_news_review_items`:
  - `POST /dashboard/api/internal/daily-news/items/{item_id}/publish`
- implemented server-side publish in `dashboard/daily_news.py`
  - validates copy with the same channel safety guard
  - publishes via configured bot token to `CHANNEL_ID`
  - falls back from `sendPhoto` to plain text post if image publish is rejected
  - marks row `failed` and emits control event on publish failure
- switched `ops/n8n/workflows/amonora_daily_news_generate.json` from manual approval handoff to:
  - direct internal publish request
  - operator log after successful publish
  - fallback evergreen candidate branch when slot has no fresh relevant news or hits duplicate/cooldown
  - simpler candidate flow by routing `Limit Candidates` directly to `Sort Latest`
- left `amonora_daily_news_approval` as legacy rollback workflow and disabled it in live runtime
- updated docs:
  - `ops/n8n/README.md`
  - `documentation/RUNBOOK.md`
  - `documentation/FEATURES.md`
  - `documentation/ai/STATE.md`

## Validation

- local:
  - `python3 -m json.tool ops/n8n/workflows/amonora_daily_news_generate.json`
  - `./venv/bin/python -m py_compile dashboard/daily_news.py dashboard/main.py`
  - `./venv/bin/python -m unittest tests.test_dashboard_internal_daily_news_api tests.test_dashboard_internal_channel_api`
- production:
  - uploaded targeted archive to core host and extracted into `/opt/amonora_bot`
  - restarted `amonora-dashboard.service`
  - updated live `n8n` sqlite workflow payloads:
    - `amonora_daily_news_generate -> active=1`
    - `amonora_daily_news_approval -> active=0`
  - restarted `amonora-n8n.service`
  - smoke checks:
    - `GET /dashboard/api/internal/daily-news/history -> 200`
    - `POST /dashboard/api/internal/daily-news/items/nonexistent/publish -> 400 Daily news item not found`
    - `systemctl is-active amonora-dashboard.service -> active`
    - `systemctl is-active amonora-n8n.service -> active`

## Ops note

- attempted one manual `n8n execute` run for the generate workflow, but the standalone CLI execution collided with the live task-broker port `5679` while the production service was already active; runtime was left healthy and the next scheduled slot will exercise the new path naturally
- production backup path before rollout:
  - `/root/codex-backups/task158-daily-news-autopublish-20260403-085258`
