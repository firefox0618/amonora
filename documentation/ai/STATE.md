# STATE.md

## Current phase
Phase 2 — AI operating layer

## Current status
Canonical documentation updated and simplified (April 13, 2026):
- PRODUCT_OVERVIEW, ARCHITECTURE, DOMAIN, REPO_RULES, RUNBOOK, FEATURES, PUBLIC_SURFACES — сокращены и упрощены
- Продукт: `Amonora` (не `Amonora Connect` — branding normalized Apr 10)
- VPN-ноды: Германия (3x-ui), Дания (Xray core), Эстония (reserve)
- Оплата: Stars + Platega (auto СБП/крипто) + ручной fallback + Баланс
- 4 бота: main, support, control, test

## Recent changes (chronological)
- Apr 13: Documentation audit — reverted incorrect `Amonora Connect` renaming, simplified all canonical docs
- Apr 12: `dashboard/ui` users slice improvements, campaign analytics date windows
- Apr 11: Estonia restored as hidden reserve-region (`est.amonoraconnect.com`)
- Apr 11: `@amonora_bot` migrated to v2 UX router, promo codes + gift subscriptions MVP
- Apr 10: Campaign analytics integrated, test-bot state-aware `/start` flow
- Apr 7: Analytics event debounce, event-time attribution, promo disabled
- Apr 5: Estonia = infra-only (later reverted), request-trace, backup/restore live
- Mar 29: Estonia → AmneziaWG (later reverted), Denmark MTProxy migration
- Mar 25: Test profiles (Android/iOS), test-bot rotation
- Mar 21: Denmark golden-node hardening
- Mar 20: Denmark standalone Xray core rollout

## Completed tasks
Tasks 001–140+ completed. Full list in `ai/TASKS/`.

## What needs live verification
- Analytics/dashboard surfaces need periodic live verification on production data
- Actual bot_url on client page (`@amonora_v_2_0_bot` vs `@amonora_bot`)
- Backup governance maturity
- Off-host backup replication
