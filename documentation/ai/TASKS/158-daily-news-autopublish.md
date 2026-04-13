## Context

Experimental `amonora_daily_news_*` workflows were active in production, but the channel still had no daily post flow that could run end-to-end without manual intervention. The repo-side migration away from `Google Sheets` was already prepared, yet the live behavior still depended on approval-style orchestration and could leave the schedule empty.

## Scope

- add a dashboard internal publish seam for `daily_news_review_items`
- switch `amonora_daily_news_generate` from approval handoff to direct auto-publish
- add a fallback evergreen branch when no relevant fresh news candidate is available for a slot
- keep small operator logging in approval/control chat without making publication depend on it
- update docs to reflect the new experimental runtime behavior

## Constraints

- keep `daily_news` experimental and separate from core channel-MVP
- do not remove the legacy approval workflow file; it may remain as rollback evidence
- preserve shared-secret dashboard internal auth
- keep publication through server-side bot credentials, not new secrets embedded in repo

## Acceptance criteria

- `daily_news` can publish without manual `да/нет` approval
- missing or duplicate news candidates no longer leave the slot empty
- internal dashboard endpoint updates `daily_news_review_items` to `posted`
- docs mention the new autopublish/fallback behavior and related runtime checks

## Validation

- `python -m py_compile` for touched dashboard files
- `python -m unittest tests.test_dashboard_internal_daily_news_api`
- `python -m json.tool` for updated workflow JSON
- production rollout with workflow reimport/update and service restarts
