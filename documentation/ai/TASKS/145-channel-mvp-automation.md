# 145 — Channel MVP Automation

## Context

Нужен первый production-ready automation контур для публичного канала `Amonora`, не как отдельный медиа-проект, а как операторский pipeline:

- тема задаётся вручную;
- `n8n` только оркестрирует расписание;
- Python-код генерирует и публикует;
- `@amonora_control_bot` остаётся operator surface для review/approve;
- переходы из канала атрибутируются отдельно от referral/campaign логики.

## Scope

В рамках задачи:

- `channel_content_items` и `channel_post_touches` в PostgreSQL;
- internal `dashboard` endpoints для generate/publish;
- OpenAI draft generation + safety validation;
- owner/admin `/channel` surface в `@amonora_control_bot`;
- `post_<token>` parsing в `@amonora_bot`;
- trial/payment attribution для channel touches;
- repo-managed `n8n` workflow exports;
- docs + tests.

## Constraints

- `n8n` не хранит business-state;
- генерация тем полностью ручная, без авто-поиска новостей;
- media/albums не входят в `v1`;
- tracked channel attribution не ломает `ref_<code>` и текущий broadcast CTA flow;
- публикация идёт через `@amonora_control_bot`, у которого уже есть права в канале.

## Acceptance

- оператор может создать тему в `/channel`, получить черновик, отредактировать, approve и опубликовать;
- `n8n` может по расписанию вызывать generate/publish HTTP hooks;
- risky public wording режется safety-validator'ом;
- post CTA ведёт в `@amonora_bot?start=post_<token>`;
- первый `/start post_<token>` создаёт touch, а последующий trial/payment отмечает conversion на свежем touch.
