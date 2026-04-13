# 157. Daily News Internal Store Migration Result

## Done

- added PostgreSQL model `daily_news_review_items` in `backend/core/models.py`;
- added internal dashboard daily-news seam in `dashboard/daily_news.py` plus new endpoints in `dashboard/main.py`:
  - `GET /dashboard/api/internal/daily-news/history`
  - `POST /dashboard/api/internal/daily-news/items/upsert`
  - `POST /dashboard/api/internal/daily-news/items/{item_id}/review-message`
  - `POST /dashboard/api/internal/daily-news/items/{item_id}/status`
- rewired `ops/n8n/workflows/amonora_daily_news_generate.json` and `ops/n8n/workflows/amonora_daily_news_approval.json` away from `Google Sheets` nodes to internal `HTTP Request` nodes backed by the new seam;
- updated `ops/n8n/README.md`, `documentation/RUNBOOK.md`, and `documentation/ai/STATE.md`.

## Validation

- `./venv/bin/python -m py_compile backend/core/models.py dashboard/daily_news.py dashboard/main.py`
- `./venv/bin/python -m unittest tests.test_dashboard_internal_channel_api tests.test_dashboard_internal_daily_news_api`
- `python3 -m json.tool ops/n8n/workflows/amonora_daily_news_generate.json`
- `python3 -m json.tool ops/n8n/workflows/amonora_daily_news_approval.json`

## Important Note

This result is repo-side only until a separate production rollout happens.  
The live core `channel-MVP` runtime is already repaired, but the experimental `daily_news` runtime on the server will keep using its old imported workflow copies until those are explicitly re-imported or updated in production `n8n`.
