# 157. Daily News Internal Store Migration

## Context

After the April 3 runtime repair, the core repo-managed channel-MVP workflows were restored in production.  
However, the separate experimental `amonora_daily_news_generate` / `amonora_daily_news_approval` workflows still depended on `Google Sheets` nodes in `n8n`.

That dependency caused a credentials failure in the live runtime:

- `Node does not have any credentials set`
- `Issue on initial workflow activation try of "amonora_daily_news_approval"`

## Goal

Remove the experimental daily-news path's dependency on `Google Sheets` and migrate its review-state storage to the same architectural pattern the repo already prefers for `n8n`:

- `n8n` stays orchestration-only;
- persistent state lives in PostgreSQL;
- workflows talk to the product/backend layer through internal HTTP endpoints.

## Scope

- add a persistent PostgreSQL model for daily-news review items;
- add internal dashboard endpoints for:
  - reading history,
  - upserting generated review items,
  - storing the approval message id,
  - updating posted/rejected status;
- update the experimental `amonora_daily_news_*` workflow JSON files to use those internal endpoints instead of `Google Sheets`;
- update the `n8n` operational docs.

## Constraints

- do not disturb the already repaired core `channel-MVP` workflows;
- keep the change small and reversible;
- be explicit that this is still an experimental path and not part of the core posting MVP;
- do not claim production rollout unless the workflow JSONs and backend changes are actually deployed.

## Acceptance Criteria

- repo workflow JSONs for `amonora_daily_news_generate` and `amonora_daily_news_approval` contain no `googleSheets` nodes;
- the repo contains a PostgreSQL-backed internal daily-news seam in dashboard/backend code;
- internal API tests cover the new endpoints;
- docs no longer describe `Google Sheets` as the required storage for this path.
