# TASK 144 — Mobile override and node alert noise result

Дата: 30 марта 2026

## Что сделано

- admin-only `Мобильный` режим в основном `@amonora_bot` теперь может отдавать fixed shared link через env-override:
  - `MOBILE_MODE_OVERRIDE_LINK_DE`
  - `MOBILE_MODE_OVERRIDE_LINK_DK`
- при такой выдаче бот не пересобирает live per-device `vless://` payload, а отдает operator-defined link и переименовывает fragment в `☁️ Amonora`
- Estonia runtime monitoring больше не зависит от legacy `3x-ui/xray` signal после перевода ноды на `AmneziaWG`
- local `core` node больше не шлёт node-level `degradation` alerts в control flow; для core остаются только реальные `down` и service-level incidents

## Validation

- targeted unit tests passed for:
  - mobile override fragment rewrite
  - local core node noise suppression
  - Estonia legacy runtime suppression in dashboard state
- live core rollout applied:
  - `amonora-bot.service` restarted successfully
  - `amonora-dashboard.service` restarted successfully
  - `EE` snapshot now reports `dashboard_state = active`
  - `Core` snapshot now reports `dashboard_state = active`
- live env now carries the same override link for `DE` and `DK` mobile mode on core host

## Notes

- this is intentionally an admin-only mobile path and does not replace normal per-user stable/reserve key delivery
- old historical `control-health:node:2` events remain in the DB as resolved evidence, but new local-core degradation noise should stop after the rollout
