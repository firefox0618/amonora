# Deployment и перенос

> Supporting reference document. Use [RUNBOOK.md](/home/dextrmed/projects/amonora_bot/documentation/RUNBOOK.md) and the `documentation/ops/` layer as canonical current-state operational docs first.

## Основной принцип

Развёртывание Amonora должно быть повторяемым и безопасным:

- не трогать SSH без необходимости
- не менять пароль root в рамках обычного деплоя
- сначала проверять нагрузку
- только потом обновлять сервисы

## Что проверять перед выкладкой

### На backend-сервере

- `uptime`
- `free -h`
- `df -h`
- `systemctl is-active ...`

### На VPN-нode

- доступность `ssh`
- доступность tunnel-адреса панели с backend
- состояние панели `3x-ui`

## Текущая схема выкладки backend

1. Проверить нагрузку сервера.
2. Собрать свежий проект.
3. Если direct `git push` из текущей среды не проходит, использовать backend-host как GitHub bridge: сервер `46.21.81.186` подтверждённо умеет ходить в `github.com` своим ключом `/home/ubuntu/.ssh/id_github_amonora`.
4. Обновить файлы в `/opt/amonora_bot`.
4. Обновить `.env`, если менялись переменные.
5. Обновить зависимости.
6. Прогнать compile / smoke-check.
7. Перезапустить нужные systemd-сервисы.
8. Проверить HTTP-вход в dashboard и логи ботов.

## Подтверждённый WSL rollout path

По состоянию на 24 марта 2026 года подтверждено:

- из WSL надёжный вход на backend идёт через Windows OpenSSH wrapper, а не через raw Linux `ssh`;
- live runtime tree на backend: `/opt/amonora_bot`;
- ранее описанный `/opt/amonora_bot_git` сейчас отсутствует, вместо него на сервере виден fallback checkout `/opt/amonora_bot_git.preclean-20260322-065219`;
- на backend уже использовались archive-based deploy scripts вида `/opt/remote_deploy_*.sh` и архивы `/opt/amonora-*.tgz`.

Практический вывод:

- для выкладки безопаснее считать основным сценарий `commit -> push (или backend GitHub bridge) -> archive deploy -> targeted restart -> smoke-check`;
- для доставки артефактов на backend из WSL нужно предпочитать Windows `ssh.exe/scp.exe` wrappers;
- для больших repo-backed релизов нельзя полагаться только на старую память о `/opt/amonora_bot_git`, нужно сначала проверить актуальный runtime shape на сервере.

## Текущая схема миграции на новый VPS

1. Подготовить новый сервер пакетами и swap.
2. Развернуть PostgreSQL.
3. Снять финальный dump с прежнего backend-контура.
4. Восстановить базу на новом сервере.
5. Перенести проект и `.env`.
6. Поднять dashboard.
7. Остановить старые polling-боты.
8. Запустить polling-боты на новом сервере.
9. Отключить лишние сервисы на старом хосте.

## Что нельзя забыть

- финальный dump БД лучше делать уже после остановки старых polling-ботов
- support-бот хранит тикеты в PostgreSQL, отдельный JSON-файл больше не источник истины
- перед production rollout `Amonora Control` нужен ротированный `AMONORA_CONTROL_BOT_TOKEN`
- если меняется архитектура серверов, нужно обновлять `managed_servers`

## Критичные systemd-сервисы

### Backend

- `amonora-bot.service`
- `amonora-test-bot.service`
- `amonora-support-bot.service`
- `amonora-control-bot.service`
- `amonora-dashboard.service`
- `postgresql.service`
- `nginx`

### VPN-нода

- `docker`
- `containerd`
- `ssh`
- контейнер `3x-ui`

## Что делать после переноса

- проверить вход в дашборд
- проверить `/start` в основном боте
- проверить support-бот
- проверить создание устройства
- проверить доступность `XUI_URL_DE` по адресу из backend `.env`
- прогнать `python tests/test_region_integrity.py`
- при необходимости прогнать `python reconcile_vpn_regions.py --apply --retire-ee-cleanup`
