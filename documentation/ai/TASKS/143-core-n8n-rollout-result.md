# TASK 143 — Core n8n rollout result

Дата: 29 марта 2026

## Что сделано

На core host `46.21.81.186` поднят отдельный `n8n` runtime как lightweight automation layer для operator-side сценариев, без публикации наружу через `nginx`.

Принцип rollout:

- broken global npm install не использовался как финальный runtime;
- `n8n` установлен изолированно в `/opt/n8n`;
- service запускается отдельным user `n8n`;
- listener оставлен только на `127.0.0.1:5678`, чтобы не открывать новый публичный surface без отдельного auth/edge-решения;
- resource limits зафиксированы сразу, потому что core host уже несёт продуктовые web/bot сервисы.

## Runtime

- host: `46.21.81.186`
- service: `amonora-n8n.service`
- version: `2.7.4`
- install path: `/opt/n8n`
- env file: `/etc/n8n/n8n.env`
- data dir: `/var/lib/n8n`
- service user: `n8n`
- bind: `127.0.0.1:5678`
- memory cap: `512M`
- CPU quota: `50%`
- timezone: `Asia/Yekaterinburg`
- executions prune: enabled
- executions max age: `168` hours
- executions max count: `5000`

## Validation

- `systemctl status amonora-n8n.service` -> `active (running)`
- `ss -ltnp` confirms `127.0.0.1:5678`
- `curl -I http://127.0.0.1:5678` returns HTTP response from live runtime
- first-start migrations completed without reverting other core services
- host memory still has wide headroom after rollout

## Known limits

- current rollout is intentionally local-only; there is no public `nginx` route or domain for `n8n` yet
- `n8n` logs a Python task-runner warning on startup; this does not block the main UI/runtime, but Python execution is not part of the current baseline
- this host should use `n8n` only for light automation such as hourly Telegram posting / simple workflows, not heavy scraping or AI/browser jobs

## Rollback

- `systemctl stop amonora-n8n.service`
- `systemctl disable amonora-n8n.service`
- удалить `/etc/systemd/system/amonora-n8n.service`
- удалить `/opt/n8n`
- удалить `/etc/n8n`
- удалить user data в `/var/lib/n8n`, если откат требуется полностью
