# TASK 141 — Trial Conversion Promo And Gifted Months

## Status
Completed

## Goal
Обновить post-trial conversion copy в `@amonora_bot` и включить реальные подарочные месяцы для тарифов `3 / 6 / 12 месяцев`.

## Why
Пробный доступ конвертируется слабо: пользователи берут `3 дня trial` и не доходят до оплаты. Нужен более сильный срочный оффер и фактическое совпадение между маркетинговым обещанием и длительностью доступа после оплаты.

## Context
Relevant docs and code areas:
- `documentation/FEATURES.md`
- `documentation/ai/STATE.md`
- `bot/utils/tariffs.py`
- `bot/utils/texts.py`
- `bot/handlers/tariffs.py`
- `bot/platega_flow.py`
- `dashboard/services.py`
- `control_bot/storage.py`
- `ops/access_reminders.py`

## Current behavior
До изменения тарифы `3m / 6m / 12m` давали базовые `90 / 180 / 365` дней, а post-trial reminders использовали нейтральный copy без ограниченной по времени акции.

## Desired behavior
После изменения:
- тариф `3 месяца` даёт `+1 месяц` в подарок;
- тариф `6 месяцев` даёт `+2 месяца` в подарок;
- тариф `12 месяцев` даёт `+3 месяца` в подарок;
- акция действует только с `27 марта 2026` по `7 апреля 2026` включительно, а вне этого окна продукт автоматически возвращается к обычным срокам и обычному copy;
- user-facing payment texts не расходятся с фактическим сроком доступа.

## Scope
What is included in this task.
- runtime tariff duration updates;
- tariff/payment/reminder copy updates;
- trigger default template updates;
- focused automated tests;
- state/features documentation updates.

## Out of scope
What must not be changed here.
- цены тарифов;
- trial duration;
- полная переработка campaign editor в control bot;
- новые payment providers.

## Constraints
Important limitations:
- preserve compatibility with current tariff codes `1m / 3m / 6m / 12m`;
- do not change runtime paths, ports, or service names;
- keep operator tariff buckets stable in `dashboard/ui`;
- avoid secret/config changes for promo enablement.

## Risks
Potential regressions or sensitive areas.
- рассинхрон между marketing copy, промо-окном и `PaymentRecord.duration_days`;
- существующие user/payment texts могли остаться на старом названии тарифа;
- DB-backed trigger rules уже могли быть созданы в production и не обновятся только от изменения repo defaults.

## Acceptance criteria
Concrete conditions for completion.
- `3m / 6m / 12m` создают payment records с расширенным `duration_days`;
- `tariffs_text`, payment step texts и access reminders показывают promo offer только внутри промо-окна;
- `dashboard` runtime tariff list показывает те же effective durations;
- targeted tests cover duration math and copy expectations.

## Validation
Tests and manual checks required.
- `./venv/bin/python -m unittest tests.test_bot_copy_updates`
- `./venv/bin/python -m unittest tests.test_dashboard_business_rules`
- `PYTHONPATH=. ./venv/bin/python tests/test_access_reminders.py`
- manual smoke: открыть `Купить`, выбрать `3/6/12 месяцев`, убедиться что copy и итоговый срок выглядят согласованно.

## Deliverables
- code changes for tariff durations and promo copy
- docs updates
- short implementation summary
