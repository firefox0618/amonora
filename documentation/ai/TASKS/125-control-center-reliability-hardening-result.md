# TASK 125 RESULT — Control center reliability hardening

## Outcome
The active `Amonora Control` surface now behaves more truthfully under failure and operator race conditions, without removing the existing production seams.

## What changed
- access mutations now return structured sync results, and the API/UI can expose partial sync failure instead of silent full success;
- deep repair now performs a post-repair sync verification step and falls back to `repair_needed`, instead of reporting false success;
- VLESS and Trojan cleanup/sync flows now fall back to cross-inbound lookup when `inbound_id` is missing, reducing key drift after delete/reissue/repair;
- payment transitions now use stronger row-locking and guardrails around confirmed-payment downgrade/delete, while terminal non-confirmed transitions release held balance;
- settings now distinguish refresh/status checks from restart, reject multiline `.env` values, and surface `restart required`;
- node health now includes runtime-service degradation, so `xray / 3x-ui` failure is not masked by only healthy CPU/RAM/Disk values;
- unsafe support transfer to an unknown admin is rejected;
- support close and reply UX were made more truthful about Telegram delivery guarantees;
- settings now expose `roles / notifications / integrations` as active tabs instead of leaving those parts of `amonora_control_tz_v5.md` undocumented in the UI;
- traffic copy now labels the synthetic 24h event curve as operational activity instead of pure live traffic.

## Validation completed
- `./venv/bin/python -m compileall dashboard bot support_bot control_bot`
- `./venv/bin/python -m unittest tests.test_dashboard_acr_fixes tests.test_dashboard_vpn_repair tests.test_payment_finalization tests.test_confirm_external_payment_record tests.test_dashboard_api_v2_settings_contract tests.test_dashboard_api_v2_role_access tests.test_dashboard_api_v2_support_contract`
- `dashboard/ui` TypeScript check via Windows Node runtime: `tsc --noEmit`
- `git diff --check`

## Residual risks
- support close notification is now represented truthfully, but Telegram delivery still remains an external dependency;
- region-to-node migration is safer than before, but still intentionally conservative until device metadata carries explicit node ownership everywhere;
- payment/access/device/node orchestration is more guarded, but still not a single transactional runtime across DB + node + bot seams.
