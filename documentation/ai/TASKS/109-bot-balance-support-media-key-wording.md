# 109 — Bot Balance, Support Media, and Key Wording Hardening

## Context

`Amonora Connect` still had several product seams that were correct in spirit but weak in execution:

- iOS onboarding still pointed to an outdated `Happ` link;
- mobile import guidance was fragmented and protocol-specific in the wrong places;
- user-facing bot wording still said `получить конфиг` for URI-based protocols;
- the referral system still behaved like bonus days instead of a spendable ruble balance;
- support stored only preview text for media and did not preserve Telegram attachment metadata for dashboard/admin use.

This task hardens those seams without broad repo reshaping.

## Scope

- update Happ iOS link;
- normalize mobile key-import instructions;
- rename URI-based user-facing `получить конфиг` wording to `получить ключ`;
- replace referral bonus days with ruble `Баланс`;
- add reserve/apply/release balance behavior to RUB payment flows;
- persist support attachment metadata and expose a dashboard attachment route;
- reflect the new payment/support data in legacy dashboard and `dashboard_v2`;
- update canonical docs.

## Constraints

- keep `WireGuard` wording as config / `.conf`, not key;
- do not mix `Баланс` with `Telegram Stars`;
- historical referral conversion must be additive and idempotent;
- do not store Telegram media binaries locally;
- preserve already-dirty local changes in `bot/handlers/devices.py`.

## Acceptance Criteria

- iOS Happ button opens `https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973`;
- user-facing URI flows say `Получить ключ`, while `WireGuard` still says `Получить конфиг`;
- `Личный кабинет` shows `Баланс` and available-to-spend amount;
- `1 paid referral = 50 р`, with one-time migration for already rewarded historical referrals;
- RUB manual/crypto flows show full price, balance contribution, and cash remainder;
- support stores attachment metadata and both admin UIs can open ticket attachments;
- targeted payment/support/dashboard tests pass.

## Validation

- `./venv/bin/python -m unittest -q tests.test_bot_copy_updates tests.test_support_storage tests.test_dashboard_support_attachment tests.test_referral_balance tests.test_payment_finalization tests.test_dashboard_api_v2_support_contract`
- `./venv/bin/python -m unittest -q tests.test_confirm_external_payment_record tests.test_dashboard_vpn_repair tests.test_dashboard_api_v2_contract`
- `python3 -m compileall bot support_bot dashboard backend tests documentation`
- `git diff --check`
