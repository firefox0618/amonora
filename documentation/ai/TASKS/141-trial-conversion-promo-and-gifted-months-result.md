# TASK 141 RESULT — Trial Conversion Promo And Gifted Months

## Summary
В `@amonora_bot` включён conversion-oriented promo copy для post-trial follow-ups, а тарифы `3 / 6 / 12 месяцев` теперь реально выдают дополнительные месяцы доступа только в окне акции с `27 марта 2026` по `7 апреля 2026` включительно, а не бессрочно.

## Implemented
- added date-gated tariff promo helpers and effective durations in `bot/utils/tariffs.py`;
- updated tariff screen, payment step texts, manual payment texts, success texts, and access reminders in `bot/utils/texts.py`;
- passed marketing tariff titles into tariff purchase/payment flows in `bot/handlers/tariffs.py` and `bot/platega_flow.py`;
- aligned operator/runtime tariff durations in `dashboard/services.py`;
- refreshed default trigger templates in `control_bot/storage.py`;
- added/updated focused tests for copy and duration expectations.

## Effective durations
- `1m` -> `30` days
- `3m` -> `120` days only inside the promo window, otherwise `90`
- `6m` -> `240` days only inside the promo window, otherwise `180`
- `12m` -> `455` days only inside the promo window, otherwise `365`

## Validation
- `./venv/bin/python -m unittest tests.test_bot_copy_updates`
- `./venv/bin/python -m unittest tests.test_dashboard_business_rules`
- `PYTHONPATH=. ./venv/bin/python tests/test_access_reminders.py`

## Follow-up
- production DB-backed trigger rules should be updated if their rows already exist and should use the new copy immediately
- if the promo window changes again, update the shared date-gated promo constants and the live trigger rows together
