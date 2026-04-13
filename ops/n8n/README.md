# n8n Workflows

Репозиторий хранит lightweight orchestration для канального MVP, плюс отдельные
экспериментальные workflow для ежедневного AI-автопостинга (не часть core MVP).

Правила этого слоя:

- `n8n` остаётся orchestrator-only для core MVP;
- бизнес-логика, OpenAI generation, safety validation и публикация живут в Python-коде;
- workflows используют только `Schedule Trigger` + `HTTP Request`;
- source of truth по состояниям хранится в PostgreSQL, а не в `n8n`.

## Workflows

- `workflows/generate_due_channel_drafts.json`
  - каждый день в `12:00` `Asia/Yekaterinburg`
  - вызывает `POST /dashboard/api/internal/channel/generate`
- `workflows/publish_approved_channel_posts.json`
  - каждые `5` минут
  - вызывает `POST /dashboard/api/internal/channel/publish`
- `workflows/remind_missing_channel_content.json`
  - каждый день в `09:00` `Asia/Yekaterinburg`
  - вызывает `POST /dashboard/api/internal/channel/generate` с `notify_missing_content=true`

## Experimental daily news workflows

- `workflows/amonora_daily_news_generate.json`
  - запускается по `Europe/Moscow` в `10:12`, `14:18` и `19:37`
  - использует разные дневные слоты: утро = полезный инфо-пост, день = короткий лёгкий пост, вечер = основной пост
  - собирает RSS/RSSHub, а если релевантной новости нет или она дублируется, строит резервный evergreen-пост
  - генерирует HTML-пост через OpenRouter и публикует его автоматически через внутренний dashboard seam `/dashboard/api/internal/daily-news/*`
  - пишет историю в PostgreSQL `daily_news_review_items` и после публикации отправляет короткий лог в approval/control chat
- `workflows/amonora_daily_news_approval.json`
  - legacy approval workflow
  - больше не нужен для ежедневного автопостинга и может оставаться выключенным

## Required env

- `AMONORA_INTERNAL_CHANNEL_WEBHOOK_SECRET`
- `AMONORA_DASHBOARD_BASE_URL`
  - default target in workflows: `http://127.0.0.1:8088`
- `OPENROUTER_API_KEY`
- `CONTROL_APPROVAL_CHAT_ID` / `CONTROL_APPROVAL_CHAT_IDS`
- `TG_APPROVAL_BOT_TOKEN`
- `AMONORA_INTERNAL_CHANNEL_WEBHOOK_SECRET`

## Import notes

- `n8n` runtime на core host сейчас local-only (`127.0.0.1:5678`)
- после импорта workflows нужно проверить:
  - секрет в header `x-amonora-internal-secret`
  - dashboard origin
  - timezone `Asia/Yekaterinburg`
  - что dashboard на своём env действительно может создать таблицу `daily_news_review_items`
  - что `amonora_daily_news_generate` активирован, а legacy `amonora_daily_news_approval` не мешает автопайплайну
