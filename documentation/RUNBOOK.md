# RUNBOOK

## Зачем нужен этот документ

Этот документ фиксирует базовую карту запусков текущего продукта.

Здесь собраны ответы на пять практических вопросов:

- какие сервисы запускаются отдельно;
- на каких портах они живут;
- через что поднимаются;
- от чего зависят;
- что проверять в первую очередь, если сервис не работает.

> По состоянию на 19 марта 2026 года основные unit names, внутренние порты и runtime paths уже подтверждены live-инвентаризацией. Отдельной сверки всё ещё требуют backup-процессы, retention и часть вторичных ops-деталей.

## Общая схема запуска

В текущем контуре отдельно запускаются:

- `bot`
- `test_bot`
- `support_bot`
- `control_bot`
- `dashboard`
- `dashboard/ui`
- `landing`
- `n8n`
- `grafana`
- фоновые процессы из `ops`

Поверх веб-сервисов стоит `nginx`, который маршрутизирует внешний трафик на внутренние порты.

Для Germany важно помнить ещё один runtime-факт, подтверждённый 24 марта 2026 года:

- `3x-ui` на этой VPN-ноде сейчас живёт как Docker container `ghcr.io/mhsanaei/3x-ui:latest` из `/opt/3x-ui/docker-compose.yml`, а не как systemd unit `x-ui.service`;
- персистентный DB-layer остаётся bind-mounted как `/opt/3x-ui/db -> /etc/x-ui`;
- live runtime config внутри контейнера находится в `/app/bin/config.json`;
- panel API seam для device IP использует `POST /panel/api/inbounds/clientIps/{email}` и `POST /panel/api/inbounds/clearClientIps/{email}`;
- на момент этой проверки `inbound_client_ips` table существует, но current DE runtime still returns `No IP Record`, so broad live-IP visibility depends on a separate persistent panel-side access-log enable step.

> Обновление от 29 марта 2026 года: Estonia `185.88.37.71` больше не считается `3x-ui` / `Xray`-нодой. На ней снят старый `docker + 3x-ui + xray` stack, закрыты прежние `443/8443/2053/2096` VPN/panel listeners, отключены core-side units `amonora-xui-tunnel-ee.service` и `amonora-xui-ee-tunnel.service`, а новый runtime теперь состоит из `AmneziaWG` (`awg-quick@awg0`) на `51820/udp` с tunnel subnet `10.10.8.1/24`. Pre-change archive этого перевода: `/root/prechange-amneziawg-20260329-083720.tgz`.

> Обновление от 11 апреля 2026 года: этот Estonia-only infra baseline больше не является актуальной runtime-истиной. `185.88.37.71` снова поднята как `x-ui` / `Xray` VPN-нода с user-facing hostname `est.amonoraconnect.com`, outer `VLESS + Reality + TCP + xtls-rprx-vision` listener на `443/tcp` и panel на `2053/tcp` c base-path `/dashboard`, ограниченной только core host `46.21.81.186`. Для product/runtime truth нужно считать активными env-пары `XUI_URL_EE`, `XUI_USERNAME_EE`, `XUI_PASSWORD_EE`, `VPN_HOST_EE`, а unified public subscription feed теперь может выдавать `🇪🇪 #1 Эстония` как скрытый reserve-style маршрут наряду с Germany и Denmark.

> Обновление от 29 марта 2026 года, третий проход: на core host `46.21.81.186` поднят отдельный automation runtime `n8n` как `systemd` unit `amonora-n8n.service`. Текущий safe baseline: isolated install в `/opt/n8n`, service user `n8n`, локальный listener только на `127.0.0.1:5678`, env-файл `/etc/n8n/n8n.env`, user data в `/var/lib/n8n`, memory cap `512M`, CPU quota `50%`.
>
> Обновление от 1 апреля 2026 года: `n8n` больше не является strictly local-only surface. Для операторов поднят guarded HTTPS path `https://amonoraconnect.com/n8n/` через текущий `nginx` vhost `amonora-dashboard`, при этом upstream по-прежнему остаётся локальным `127.0.0.1:5678`. Внешний доступ защищён outer `HTTP Basic Auth` через `/etc/nginx/.htpasswd-n8n`, а сам `n8n` переведён на base-path-aware режим через `N8N_HOST=amonoraconnect.com`, `N8N_PROTOCOL=https`, `N8N_EDITOR_BASE_URL=https://amonoraconnect.com/n8n/`, `N8N_PATH=/n8n/`, `WEBHOOK_URL=https://amonoraconnect.com/n8n/`, `N8N_PROXY_HOPS=1`. Pre-change backup этого rollout хранится в `/opt/amonora_bot_backup/n8n-public-access-20260401-103357`.

> Обновление от 5 апреля 2026 года: Grafana больше не считается core-side operator path. Канонический операторский вход теперь `https://grafana.amonoraconnect.com`, сам `grafana-server` должен жить на Estonia infra-host `185.88.37.71`, outer auth остаётся через `nginx` + `/etc/nginx/.htpasswd-grafana`, а datasource идёт не в публичный PostgreSQL, а через Estonia-side `amonora-grafana-db-tunnel.service` на loopback `127.0.0.1:15432 -> core 127.0.0.1:5432`. На `core` остаются PostgreSQL и `amonora-analytics-refresh.timer`, а старый `/grafana/` path должен только редиректить на новый hostname.
>
> Практическая runtime-проверка того же rollout: файл outer Basic Auth `/etc/nginx/.htpasswd-grafana` на Estonia должен быть читаем nginx worker'ом. Без этого безлогинный вход будет выглядеть как нормальный `401`, а реальная проверка логина даст `500`. Безопасный baseline: `root:www-data` и `0640`.

## Базовые operational rules

При любом изменении нужно держать в голове несколько базовых правил:

- нет изменения без backup;
- нет деплоя без записи;
- одно изменение за раз;
- без явного rollback-плана опасные изменения не делать;
- старых VPN-пользователей нельзя массово ломать ради нового конфига;
- новые inbound-профили сначала добавляются параллельно, а не поверх старых.

Детальные версии этих правил лежат в:

- `ops/DEPLOY_RULES.md`
- `ops/ROLLBACK.md`
- `ops/BACKUP_VERIFICATION_2026-03-19.md`
- `ops/RESTORE_READINESS_2026-03-19.md`
- `ops/BACKUP_GOVERNANCE_AND_RETENTION_MAP_2026-03-19.md`
- `ops/OFF_HOST_BACKUP_AND_PROVIDER_SNAPSHOT_VERIFICATION_2026-03-19.md`
- `vpn/VPN_CONFIG_STRATEGY.md`
- `vpn/XRAY_3XUI_ACTION_PLAN.md`
- `ops/PRODUCTION_RUNTIME_INVENTORY_2026-03-19.md`

## Backup Reality

По live-проверке от 19 марта 2026 года подтверждено:

- локальные backup-артефакты PostgreSQL существуют на core host в `/opt/amonora_bot/backups`;
- локальные backup-артефакты `3x-ui` подтверждены для Germany в `/opt/3x-ui/backups`, а для Estonia сохранены только как historical pre-migration artifacts до перевода на `AmneziaWG`;
- restore-скрипты PostgreSQL существуют на core host;
- при этом recurring automation, retention и off-host replication подтверждены не полностью.

Практическое правило:

- считать backup-контур частично рабочим, но не достаточно зрелым для рискованных изменений без отдельного pre-change backup.

> Обновление от 3 апреля 2026 года, repo-side hardening: в репозитории появился server-side backup path, который больше не завязан только на Windows Scheduled Task. Базовый core-side PostgreSQL dump теперь может выполняться через `ops/backup/core_pg_backup.sh` + `ops/systemd/amonora-core-pg-backup.{service,timer}`, а повторяемый pull backup для удалённых артефактов — через `ops/backup/remote_artifact_backup.sh` + `ops/systemd/amonora-remote-artifact-backup@.{service,timer}` с per-instance env в `/etc/amonora/backup.d/%i.env`. Для restore-readiness repo-side теперь также есть `ops/backup/restore_validation_check.sh` + `ops/systemd/amonora-restore-validation.{service,timer}`; сам drill должен писать не только legacy `status/restore-validation.json`, но и `status/restore-proof.json` с явными полями `proof_kind / proof_status / proof_scope`, а dashboard должен считать `healthy` только machine-readable proof payload, а не markdown-отчёты и не старый JSON без proof-полей. Если app-side DB user не имеет `CREATEDB`, production-safe fallback теперь идёт через wrapper-скрипты `ops/backup/{pg_dump,createdb,dropdb,psql}_as_postgres.sh` и локальный PostgreSQL socket в `/etc/amonora/backup.env`. Старые PowerShell-скрипты в `ops/local/*.ps1` нужно считать legacy/local fallback, а не единственным рекомендуемым orchestration path.

## Restore Reality

По live-проверке от 19 марта 2026 года подтверждено:

- на core host существует реальный PostgreSQL restore path на уровне server-side скриптов;
- этот path всё ещё зависит от конкретных артефактов и скрытых operational assumptions;
- для Germany `3x-ui` есть backup-входы, но явный production-side restore flow документирован слабее; для Estonia после перевода на `AmneziaWG` restore path уже должен опираться не на `x-ui.db`, а на server config в `/etc/amnezia/amneziawg/awg0.conf` и архив `/root/prechange-amneziawg-20260329-083720.tgz`.

Практическое правило:

- считать restore readiness частично реальной, но хрупкой;
- не принимать наличие restore-скриптов за гарантию безопасного отката;
- перед рискованными изменениями делать явный pre-change backup независимо от существующих артефактов.
- dashboard-side `restore readiness` теперь должен трактоваться как `unknown`, пока server-side drill не создал свежий `restore-proof.json` с реальным `temporary_database_restore` proof для `core_pg`.

> Обновление от 20 марта 2026 года: для Denmark host `81.17.159.58` / `dk.amonoraconnect.com` отдельно подтверждён pre-change backup и post-change runtime archive при переводе узла с `x-ui` на standalone `Xray core`. Эти артефакты не означают, что Denmark уже встроена в продуктовый provisioning flow, но они подтверждают rollback evidence для самой server-side операции.

> Обновление от 20 марта 2026 года, второй проход: product flow для VLESS теперь умеет работать с Denmark через отдельный provider seam (`xray_core`), без возврата Denmark в `x-ui`.

> Обновление от 21 марта 2026 года, третий проход: golden-node hardening pass завершён. Denmark теперь подтверждена как текущая anti-DPI нода с outer `Reality` listeners на `443/8443`, inner `XHTTP` inbounds `@xhttp-dk-primary` / `@xhttp-dk-reserve`, camouflage `www.apple.com`, primary path `/api/v1/updates`, reserve path `/graphql`, `packet-up`/`packet-up`, `fingerprint = chrome`, `loglevel = none`, server-side DoH upstreams (`cloudflare-dns.com`, `dns.sb`, `localhost`) и MTU policy `1400` default / `1420` fallback. Для стабильного provider-based automation path `core -> Denmark` на DK также требуется явный `ufw allow` для core host `46.21.81.186` на `22/tcp` перед общим `ufw limit`, иначе burst-сценарии create/repair/delete могут ловить `connection refused`. Germany и Estonia в этом проходе не мигрировались на standalone `Xray core`, но получили safe baseline: `bbr`, `tcp_fastopen = 3`, `tcp_mtu_probing = 1`, buffers `33554432`, `nofile = 65535`, persistence-safe `sniffing.enabled` через `x-ui.db`, `22/tcp` под `ufw limit`, shielding public panel ports `2053/2096`, и persistent `bittorrent` block. Official client pack artifacts теперь лежат в `documentation/vpn/client-packs/*`, а операторский итог опубликован в knowledge как `ops/DENMARK_GOLDEN_NODE_REPORT_2026-03-21.md`.

> Обновление от 25 марта 2026 года, четвёртый проход: на Germany и Denmark выкачены отдельные admin-only test profiles для Android и iPhone без замены действующих user-facing routes. Germany получила два новых `3x-ui`-backed `VLESS + Reality + TCP` inbound на `9443` и `10443` через persistent `x-ui.db`, с profile names `amonora-test-android-tcp` и `amonora-test-iphone-tcp`. Denmark получила два новых standalone `Xray core` profile в `/usr/local/etc/xray/amonora_dk_meta.json`: `android_test` и `ios_test`, с outer listeners `9443` / `10443`, inner tags `@xhttp-dk-android-test` / `@xhttp-dk-ios-test` и paths `/api/v2/android-sync` / `/api/v2/ios-sync`. Existing Germany `443/8443` и Denmark `primary/reserve` не заменялись, а новые профили считаются только controlled test surface для админов до отдельной compatibility-проверки. Повторяемый rollout path теперь зафиксирован в `ops/local/rollout_vpn_test_profiles_2026_03_25.py`, а операторский итог — в `documentation/ai/TASKS/131-vpn-test-profiles-android-ios-rollout-result.md`.

> Обновление от 25 марта 2026 года, пятый проход: поверх этих test profiles поднят отдельный `amonora-test-bot.service`. Это отдельный polling-bot `python -m test_bot.main`, который читает token из `AMONORA_TEST_BOT_TOKEN`, допускает только allowlist Telegram ID (`AMONORA_TEST_BOT_ALLOWED_TELEGRAM_IDS`, fallback на `ADMIN_IDS`) и отдаёт только 4 admin-only тестовых конфига с `vless://` ссылками и QR. Основной `amonora-bot.service` при этом не заменяется и не несёт на себе новый test surface.

> Обновление от 25 марта 2026 года, шестой проход: test-bot mobile rotation завершён без затрагивания `amonora-bot.service`. `amonora-test-bot.service` теперь отдаёт ровно `8` admin-only mobile test profiles: Germany `9443/10443` на `VLESS + Reality + TCP` с `www.microsoft.com`, Denmark `9443/10443` на outer `Reality + TCP` + inner `XHTTP` с live paths `/api/v1/updates` и `/graphql`, и Estonia как полностью repurpose-нутая test-only mobile node на `connect.amonoraconnect.com`, где `443` занят `VLESS + Reality + TCP`, а `8443` — `Trojan + TLS`. Это controlled test surface для mobile validation; основной пользовательский бот и его боевые routings не менялись.

> Обновление от 29 марта 2026 года, второй проход: после перевода Estonia на `AmneziaWG` test-bot больше не должен считаться только `vless://` / `trojan://` витриной. Для безопасного AWG-теста он теперь может читать server-side client config из env-path `AMONORA_TEST_BOT_AWG_PHONE_CONFIG_PATH` и отдавать его как QR/text payload без коммита приватного ключа в репозиторий. Базовый тестовый файл на core-side path должен храниться вне git, например `/opt/amonora_bot/secrets/test_bot/ee_awg_my_phone.conf`.

> Обновление от 26 марта 2026 года: Эстония допущена к repurpose из test-only VPN-ноды в публичный web-edge для `amonoraconnect.com`, если требуется сменить внешний IP сайта без переноса backend. Безопасный вариант такого cutover: на `185.88.37.71` поднимается только `nginx` TLS/reverse-proxy слой, который принимает `amonoraconnect.com` / `www.amonoraconnect.com` и прозрачно проксирует `landing`, `dashboard`, `bridge/access` и `Platega webhook` обратно на core host `46.21.81.186`. В этом режиме backend, PostgreSQL, боты и внутренние порты остаются на core, а меняется только публичный web-entry IP. Repo-side edge config для такого rollout хранится в `ops/nginx/amonora-estonia-web-edge.server.conf`. Для работающего upstream path core host должен явно allowlist-ить `185.88.37.71` на `80/tcp` и `443/tcp` поверх существующего Cloudflare-only edge policy.

> Обновление от 26 марта 2026 года, второй проход: на Denmark дополнительно поднят отдельный Telegram-only `MTProto` proxy через `mtg` как `systemd` unit `amonora-dk-mtg.service`. Он не заменяет и не мультиплексирует действующий `Xray` на `443/8443`. Из-за того, что Denmark test listeners уже занимают `9443/10443`, MTProto proxy вынесен на отдельный публичный порт `11443/tcp`. Runtime config живет в `/etc/mtg.toml`, binary — `/usr/local/bin/mtg`, rollout result зафиксирован в `documentation/ai/TASKS/136-denmark-mtproto-proxy-rollout-result.md`.
>
> Обновление от 29 марта 2026 года: Denmark Telegram proxy переведён с `mtg v2` на официальный `Telegram MTProxy`, потому что `@MTProxybot` не принимает `mtg` FakeTLS secret и `mtg v2` не поддерживает `adtag`. Текущий unit — `amonora-dk-mtproxy.service`, binary — `/usr/local/bin/mtproto-proxy`, runtime data — `/etc/mtproxy/{proxy-secret,proxy-multi.conf,secret.hex}`. Публичный listener остаётся на `11443/tcp`, старый `amonora-dk-mtg.service` отключён, а pre-change backup лежит в `/root/task143-denmark-mtproxy-adtag-migration-20260329-165455`. На Ubuntu 24.04 runtime потребовал локальный source patch в `common/pid.c`, потому что upstream assert на `pid <= 65535` падал при текущем `kernel.pid_max = 4194304`.

## Backup Governance

По live-проверке от 19 марта 2026 года:

- backup-классы реально существуют для PostgreSQL, `3x-ui`, dashboard/nginx snapshots и части operational JSON-артефактов;
- governance этого контура пока не выглядит полностью централизованным;
- retention видна скорее как накопление артефактов, а не как явно управляемая policy;
- off-host backup destination не подтверждён.

Практическое правило:

- считать backup governance частично зрелой, но ещё не достаточно сильной для доверия “по умолчанию”;
- сохранять explicit pre-change backup discipline до отдельного усиления governance.
- при rollout server-side backup path писать machine-readable status files в `${DASHBOARD_BACKUP_ROOT}/status/{core|vpn_de|vpn_ee|vpn_dk}.json`, чтобы dashboard видел не только наличие файлов, но и runner/off-host sync signal.

Отдельно подтверждён Denmark runtime backup:

- on-host pre-change backup directory:
  - `/root/task105-backup-20260320-183931`
- on-host runtime archive:
  - `/root/task105-dk-runtime-20260320-1845.tgz`
- local off-host copy:
  - `C:\\Ops\\Backups\\amonora\\vpn-dk\\2026-03-20_18-45\\task105-dk-runtime-20260320-1845.tgz`

Для Denmark provider integration на core host также важны runtime/env предпосылки:

- `VPN_HOST_DK`
- `VPN_MAX_DEVICES_PER_KEY`
- `VPN_ANTISHARING_LEASE_SECONDS`
- `VPN_ANTISHARING_SOFT_LIMIT_ENABLED`
- `XRAY_CORE_DK_SSH_HOST`
- `XRAY_CORE_DK_SSH_PORT`
- `XRAY_CORE_DK_SSH_USER`
- `XRAY_CORE_DK_SSH_KEY_PATH`
- `XRAY_CORE_DK_SSH_KNOWN_HOSTS`
- `XRAY_CORE_DK_SSH_TIMEOUT`
- `XRAY_CORE_DK_CONFIG_PATH`
- `XRAY_CORE_DK_META_PATH`

Практическое правило:

- Denmark не должна получать `x-ui` URL в managed-server конфигурации;
- Denmark больше не должна считаться test-only регионом в user-facing выборе, но `ENABLE_DK_TEST_FLOW` / `DK_TEST_TELEGRAM_IDS` можно сохранять как legacy safety toggle до полного вывода из env;
- для Denmark VLESS provisioning и repair идут через SSH-доступ к standalone `Xray core`, а не через panel login.
- для Germany persistence-sensitive hardening должен идти через `x-ui.db` + controlled restart/regeneration, а не через ручной edit generated runtime JSON.
- `VPN_MAX_DEVICES_PER_KEY` задаёт общий продуктовый предел одновременных IP на один ключ: Germany как `3x-ui`-регион читает его как `limitIp`, а Denmark enforcer должен запускаться с тем же значением через `--max-devices`.
- Estonia больше не должна получать `XUI_URL_EE`, `3x-ui`-based repair/provisioning или старые hidden activation/test-bot assumptions; её текущая ops truth — это infra-host c `nginx`, `grafana-server`, `amonora-grafana-db-tunnel.service` и legacy cleanup only.
- Denmark enforcer по умолчанию читает whitelist из `/usr/local/etc/xray/amonora_dk_ip_whitelist.json`; пример формата лежит в [`ops/env/amonora_dk_ip_whitelist.example.json`](/home/dextrmed/projects/amonora_bot/ops/env/amonora_dk_ip_whitelist.example.json).
- актуальный unit-файл Denmark enforcer запускает `ops/xray_single_ip_enforcer.py` с `--max-devices 1 --lease-seconds 180 --whitelist-file /usr/local/etc/xray/amonora_dk_ip_whitelist.json --soft-limit-warnings`; для изменения лимита нужен `systemctl edit amonora-dk-single-ip-enforcer.service` или синхронное обновление unit-файла и backend `.env`.

Свежие rollback evidence этого прохода:

- Denmark:
  - pre-change:
    - `/root/amonora-golden-node-prechange-20260321-061645`
    - `/root/amonora-golden-node-prechange-20260321-061645.tgz`
  - post-change:
    - `/root/amonora-golden-node-postchange-20260321-053834`
    - `/root/amonora-golden-node-postchange-20260321-053834.tgz`
- Germany:
  - pre-change:
    - `/root/amonora-golden-node-prechange-20260321-061645`
    - `/root/amonora-golden-node-prechange-20260321-061645.tgz`
  - post-change:
    - `/root/amonora-golden-node-postchange-20260321-053115`
    - `/root/amonora-golden-node-postchange-20260321-053115.tgz`
- Estonia:
  - existing `3x-ui` backup layer before the pass:
    - `/opt/3x-ui/backups/x-ui.db.20260316-195700`
    - `/opt/3x-ui/backups/x-ui.db.20260317-220759`
    - `/opt/3x-ui/backups/config.json.20260317-220759`
  - explicit post-change snapshot:
    - `/root/amonora-golden-node-postchange-20260321-053206`
    - `/root/amonora-golden-node-postchange-20260321-053206.tgz`

## Off-Host Protection

По live-проверке от 19 марта 2026 года:

- локальные backup подтверждены;
- подтверждённой внешней репликации backup не найдено;
- по `46.21.81.186` вкладка provider backup/snapshot отсутствует;
- по `185.88.37.71` вкладка provider backup/snapshot отсутствует;
- по `213.108.20.34` provider backup доступен только как отдельная платная услуга и сейчас не активирован.

Практическое правило:

- не считать host-loss protection подтверждённой ни для одного из трёх хостов;
- не путать наличие локальных dump/artifact с реальной disaster-recovery защитой.

## Карта сервисов

### bot

Статус верификации:

- порт: подтверждено по коду как polling-сервис без HTTP-порта
- unit name `amonora-bot.service`: подтверждено live runtime

Тип:

отдельный polling-сервис Telegram-бота

Как запускается:

- Python-процесс
- через `systemd` как `amonora-bot.service`

Порт:

- не использует HTTP-порт

Зависимости:

- Telegram Bot API
- `backend`
- PostgreSQL
- VPN API / `3x-ui`
- `.env`

Что проверять, если не работает:

- активен ли процесс / `systemd` unit;
- корректен ли `BOT_TOKEN`;
- доступна ли PostgreSQL;
- проходят ли запросы к VPN API;
- нет ли ошибок в polling и startup-логах.

### support_bot

Статус верификации:

- порт: подтверждено по коду как polling-сервис без HTTP-порта
- unit name `amonora-support-bot.service`: подтверждено live runtime

Тип:

отдельный polling-сервис Telegram-поддержки

Как запускается:

- Python-процесс
- через `systemd` как `amonora-support-bot.service`

Порт:

- не использует HTTP-порт

Зависимости:

- Telegram Bot API
- `backend`
- PostgreSQL
- `.env`

Что проверять, если не работает:

- активен ли процесс / `systemd` unit;
- корректен ли `SUPPORT_BOT_TOKEN`;
- доступна ли PostgreSQL;
- проходит ли bootstrap support storage;
- сохраняются ли `attachment_*` поля у новых `SupportTicketMessage`;
- доходит ли оригинальное пользовательское медиа до support-admin chat, а не только preview;
- нет ли ошибок в polling-логах.

### control_bot

Статус верификации:

- порт: polling-сервис без HTTP-порта
- unit name: `amonora-control-bot.service`

Тип:

отдельный polling-сервис внутренних уведомлений и operational review

Как запускается:

- Python-процесс
- через `systemd` как `amonora-control-bot.service`

Порт:

- не использует HTTP-порт

Зависимости:

- Telegram Bot API
- `backend`
- PostgreSQL
- `.env`
- `dashboard.services` для status/payments/nodes screens

Что проверять, если не работает:

- активен ли `amonora-control-bot.service`;
- задан ли `AMONORA_CONTROL_BOT_TOKEN`;
- корректны ли allowlist env-переменные ролей;
- могут ли разрешённые админы открыть `@amonora_control_bot` и выполнить `/start`;
- доставляются ли auth-коды и payment review уведомления;
- работают ли `/events`, `/settings` и owner-only `/broadcast`;
- создались ли campaign/trigger/preference таблицы в PostgreSQL;
- нет ли ошибок в polling и dispatcher-логах.

### dashboard

Статус верификации:

- порт `8088`: подтверждено по коду и конфигам
- unit name `amonora-dashboard.service`: подтверждено live runtime

Тип:

backend веб-админки и API

Как запускается:

- Python / FastAPI
- через `systemd` как `amonora-dashboard.service`

Порт:

- `127.0.0.1:8088`
- подтверждён live runtime на core host

Зависимости:

- `backend`
- PostgreSQL
- `support_bot.storage`
- `.env`
- `documentation`

Что проверять, если не работает:

- слушает ли `127.0.0.1:8088`;
- поднят ли `amonora-dashboard.service`;
- доступна ли PostgreSQL;
- корректны ли env-переменные;
- owner-side `.env` mutations через dashboard теперь должны идти только через staged `apply -> restart -> verify`; если хотя бы один затронутый сервис не поднялся, backend обязан откатить `.env` и повторно поднять прежний runtime, вместо молчаливого split-brain `диск новый / runtime старый`.
- не сломалась ли auth/session логика;
- работает ли attachment route `/dashboard/support/{ticket_user_id}/messages/{message_id}/attachment`;
- доступны ли backend endpoints `/dashboard/api/v2/*`.

### dashboard/ui

Статус верификации:

- порт `3001`: подтверждено по `systemd` unit и frontend-конфигам
- unit name `amonora-dashboard-ui.service`: подтверждено live runtime

Тип:

frontend админки на Next.js

Как запускается:

- Node.js / Next.js
- через `systemd` как `amonora-dashboard-ui.service`

Порт:

- `127.0.0.1:3001`
- env path на production: `/etc/amonora-dashboard-ui.env`

Зависимости:

- `dashboard`
- `NEXT_PRIVATE_DASHBOARD_BACKEND=http://127.0.0.1:8088`
- Node runtime
- `nginx`

Текущее уточнение по routing:

- основными admin routes считаются `/login`, `/verify`, `/overview`, `/users`, `/servers`, `/traffic`, `/payments`, `/support`, `/knowledge`, `/audit`, `/settings`;
- исторические `GET /dashboard/*` page-routes больше не считаются рабочим UI и должны вести только в новый frontend-контур через compatibility redirect path.
- role-routing по состоянию control-center:
  - `support_admin` (`Менеджер`) теперь работает только через `/support`;
  - `tech_admin` использует `/overview`, `/users`, `/support`, `/servers`, `/traffic`, `/knowledge`, `/audit`, `/settings`;
  - `owner` дополнительно остаётся единственной ролью для ручных payment mutations, `.env`, delete-действий и final finance approval.

Текущее уточнение по actions:

- user actions: `trial`, `extend`, `block`, `clear access`, `sync`, `deep repair`, device create/delete;
- payment actions: status flow `awaiting_user_payment -> awaiting_admin_review -> confirmed/rejected/expired/disputed/error`;
- server actions: `restart`, `health_check`, `maintenance`, `migrate`.

Что проверять, если не работает:

- активен ли `amonora-dashboard-ui.service`;
- слушает ли `127.0.0.1:3001`;
- установлен ли `node_modules`;
- доступен ли backend `127.0.0.1:8088`;
- работают ли proxy routes `/api/proxy/*`;
- нет ли ошибок сборки или runtime Next.js.

### landing

Статус верификации:

- порт `8090`: подтверждено по коду и `nginx` конфигу
- unit name `amonora-landing.service`: подтверждено live runtime

Тип:

публичный веб-сервис

Как запускается:

- Python / Uvicorn
- отдельный Python-веб-процесс через `amonora-landing.service`

Порт:

- `127.0.0.1:8090`

Зависимости:

- `.env`
- `documentation`
- `landing/static/client-app` для tokenized public subscription page на `client.amonoraconnect.com`
- часть Python-логики из `bot` и `dashboard.finance`
- PostgreSQL для связанных сценариев оплаты
- `PLATEGA_*` env для auto `СБП/крипты`, если активен новый provider seam
- `FORCE_MANUAL_SBP_USER_FLOW=1` + `ENABLE_MANUAL_SBP_USER_FLOW=1` как emergency rollback для user-side покупки тарифа по `СБП`, если provider callback режется на edge и auto `QR` не подтверждается

Что проверять, если не работает:

- слушает ли `127.0.0.1:8090`;
- отвечает ли `/health`;
- корректны ли env-переменные;
- читаются ли markdown-документы для legal-страниц;
- собраны ли `landing/static/client-app/assets/app.js` и `landing/static/client-app/assets/app.css`;
- нет ли ошибок в webhook/payment flow;
- настроен ли callback URL провайдера на `https://amonoraconnect.com/webhooks/platega/{secret}`;
- доходит ли `POST /webhooks/platega/{secret}` до origin вообще: если в `amonora-landing.service` нет webhook-записей, а provider видит `403 {"message":"Just a moment...","error":"Forbidden"}`, значит callback режется на внешнем edge до FastAPI, и нужно либо править внешнюю provider/edge-схему, либо временно включать `FORCE_MANUAL_SBP_USER_FLOW=1`.
- если жалоба касается bridge-key flow, проверить и app-side cooldown, и `nginx` rate-limit для `POST /bridge/access`.
- если жалоба касается публичной доступности сайта в мобильной сети, помнить, что user-facing canonical web-entry сейчас переведён на `https://www.amonoraconnect.com`, тогда как provider callback seam по-прежнему совместим на apex-host;
- если жалоба касается `client.amonoraconnect.com`, проверить отдельный `nginx` vhost `ops/nginx/amonora-client.server.conf`, валидность cert для `client.amonoraconnect.com`, а также public routes `GET /api/public/subscriptions/{token}/summary`, canonical single-link route `GET /{token}`, compatibility feed-route `GET /sub/{token}` и Happ-wrapper route `GET /happ/add?sub=...` на том же `landing` runtime;
- legacy `POST /webhooks/crypto-pay/{secret}` считать по умолчанию выключенным rollback-seam: без явного env-флага он должен отвечать `410`, а не участвовать в активном продукте.

### n8n

Статус верификации:

- unit name `amonora-n8n.service`: подтверждено live runtime
- isolated install path `/opt/n8n`: подтверждено live runtime
- local listener `127.0.0.1:5678`: подтверждено live runtime
- guarded operator route `https://amonoraconnect.com/n8n/`: подтверждено live runtime

Тип:

guarded operator automation/UI runtime для workflow и ручного operator-side контроля

Как запускается:

- `node /opt/n8n/node_modules/.bin/n8n start`
- отдельный systemd unit `amonora-n8n.service`
- service user `n8n`
- внешний HTTPS-вход идёт через `nginx` vhost `/etc/nginx/sites-available/amonora-dashboard`

Порт:

- `127.0.0.1:5678`
- внешний guarded path `https://amonoraconnect.com/n8n/`

Зависимости:

- Node.js runtime на core host
- env-файл `/etc/n8n/n8n.env`
- data dir `/var/lib/n8n`
- install tree `/opt/n8n`
- локальная SQLite state/config внутри `N8N_USER_FOLDER`
- dashboard origin на `127.0.0.1:8088` для internal HTTP handoff
- shared secret `AMONORA_INTERNAL_CHANNEL_WEBHOOK_SECRET` между dashboard и `n8n`
- `nginx` route `/n8n/` внутри `/etc/nginx/sites-available/amonora-dashboard`
- outer basic-auth file `/etc/nginx/.htpasswd-n8n`
- base-path env `N8N_HOST`, `N8N_PROTOCOL`, `N8N_EDITOR_BASE_URL`, `N8N_PATH`, `WEBHOOK_URL`, `N8N_PROXY_HOPS`

Репозиторный baseline:

- `ops/n8n/workflows/generate_due_channel_drafts.json`
- `ops/n8n/workflows/publish_approved_channel_posts.json`
- `ops/n8n/workflows/remind_missing_channel_content.json`
- `ops/n8n/workflows/amonora_daily_news_generate.json`
- `ops/n8n/workflows/amonora_daily_news_approval.json`
- `ops/n8n/README.md`

Текущий channel-MVP поверх `n8n`:

- `n8n` только запускает расписание и делает `HTTP Request`
- `POST /dashboard/api/internal/channel/generate`
  - принимает optional `item_id`
  - без `item_id` сам подбирает queued items на сегодня
  - optional `notify_missing_content=true` поднимает reminder в `@amonora_control_bot`, если на день нет queued/draft/approved/published item
- `POST /dashboard/api/internal/channel/publish`
  - принимает optional `item_id`
  - без `item_id` публикует approved items с `scheduled_at <= now`
- OpenAI generation, safety-validator, publish в канал и state transitions живут в Python-коде, не в `n8n`

Нужные env для channel-MVP:

- `OPENAI_API_KEY`
- `OPENAI_CHANNEL_MODEL`
- `AMONORA_INTERNAL_CHANNEL_WEBHOOK_SECRET`
- `AMONORA_CHANNEL_DEFAULT_POST_HOUR`

Экспериментальный `daily_news` путь:

- по-прежнему не часть core-MVP и не должен блокировать основные channel workflows;
- хранит runtime-state через внутренние endpoints dashboard `/dashboard/api/internal/daily-news/*`, а не через `Google Sheets`;
- `amonora_daily_news_generate` теперь сам публикует посты в канал через внутренний endpoint dashboard, а не через ручное `да/нет` подтверждение;
- если в слоте нет релевантной новости или попался недавний дубликат, workflow строит резервный evergreen-пост, чтобы слот не оставался пустым;
- для него нужны:
  - `OPENROUTER_API_KEY`
  - `TG_APPROVAL_BOT_TOKEN`
  - `CONTROL_APPROVAL_CHAT_ID` / `CONTROL_APPROVAL_CHAT_IDS`
  - `AMONORA_INTERNAL_CHANNEL_WEBHOOK_SECRET`
- если включается после миграции со старой sheet-версии, нужно проверить, что schema auto-apply может создать таблицу `daily_news_review_items`

Что проверять, если не работает:

- активен ли `amonora-n8n.service`
- слушает ли `127.0.0.1:5678`
- не упёрся ли сервис в `MemoryMax=512M`
- не сломан ли install tree в `/opt/n8n/node_modules`
- нет ли миграций или startup ошибок в `journalctl -u amonora-n8n.service`
- по-прежнему не слушает ли `n8n` напрямую `0.0.0.0`: внешний доступ должен идти только через `nginx`
- отвечает ли `GET /n8n/` как `401` без outer auth и как `200` после outer auth
- не потерялись ли `N8N_PATH=/n8n/` и `N8N_EDITOR_BASE_URL=https://amonoraconnect.com/n8n/`, если UI/assets внезапно открываются с корня
- совпадает ли `x-amonora-internal-secret` между `/etc/n8n/n8n.env` и dashboard env
- отвечает ли local dashboard на `POST /dashboard/api/internal/channel/generate` и `POST /dashboard/api/internal/channel/publish`
- отвечает ли local dashboard на `GET /dashboard/api/internal/daily-news/history`
- отвечает ли local dashboard на `POST /dashboard/api/internal/daily-news/items/{id}/publish`
- задан ли `OPENAI_API_KEY` в env процесса dashboard/control-bot
- есть ли у `@amonora_control_bot` права администратора на публикацию в публичный канал
- не остался ли live `amonora_daily_news_approval` включённым, если ежедневный автопостинг уже переведён на auto-publish

### ops background services

Статус верификации:

- `amonora-access-reminders.service/.timer`: подтверждено по репозиторию, требует финальной сверки на production host
- `amonora-server-watchdog.service/.timer`: watchdog timer подтверждён live runtime

Тип:

служебные фоновые процессы

Что уже явно есть:

- `amonora-access-reminders.service`
- `amonora-access-reminders.timer`
- `amonora-server-watchdog.service`
- `amonora-server-watchdog.timer`
- `nginx.service`
- live web/runtime units `amonora-control-bot.service`, `amonora-dashboard-ui.service`, `amonora-landing.service`
- `amonora-n8n.service`

Как запускаются:

- через `systemd` timers и oneshot services

Что они реально делают:

- `amonora-access-reminders.service/.timer`
  - каждые 5 минут обрабатывает scheduled campaigns;
  - применяет DB-driven trigger rules;
  - сканирует деградацию нод, не-`active` локальные сервисы и user-access инциденты `vpn_repair_needed`, поднимая control-events с dedupe/recovery;
  - использует `users.last_activity_at` и user/access/device state для сегментов;
- `amonora-server-watchdog.service/.timer`
  - проверяет server/node runtime и генерирует infra alerts.

Что теперь мониторится в operator health surfaces:

- `amonora-bot.service`
- `amonora-test-bot.service`
- `amonora-support-bot.service`
- `amonora-control-bot.service`
- `amonora-dashboard.service`
- `amonora-dashboard-ui.service`
- `amonora-landing.service`
- `nginx.service`
- `amonora-access-reminders.timer`
- `amonora-server-watchdog.timer`

Порты:

- HTTP-порты не используют

Зависимости:

- Python environment
- PostgreSQL
- `.env`
- рабочий путь `/opt/amonora_bot`

Что проверять, если не работает:

- активны ли timers;
- запускаются ли oneshot services;
- корректен ли `PYTHONPATH`;
- доступны ли БД и токены;
- нет ли ошибок в cron-like логике.

## Порты и маршрутизация

Фактическая внутренняя схема такая:

- `dashboard/ui` -> `127.0.0.1:3001`
- `dashboard` -> `127.0.0.1:8088`
- `landing` -> `127.0.0.1:8090`
- `n8n` -> `127.0.0.1:5678` (upstream локальный, но операторский вход now routed через guarded `nginx` path `/n8n/`)
- `grafana` больше не должен быть активным локальным upstream на core; core-side `/grafana/*` должен только редиректить на `https://grafana.amonoraconnect.com/`

`nginx` маршрутизирует внешний трафик примерно так:

- новые админские маршруты -> `dashboard/ui`
- backend/admin API и часть auth-маршрутов -> `dashboard`
- корень сайта и публичный контур -> `landing`
- `client.amonoraconnect.com` -> отдельный `nginx` vhost на тот же upstream `landing`, со статикой `client-app`, canonical token route `/<token>` и compatibility feed-route `/sub/<token>`
- guarded operator route `/n8n/` -> local `n8n` upstream `127.0.0.1:5678`
- legacy `/grafana/*` -> `301` redirect на `https://grafana.amonoraconnect.com/`

Для analytics/Grafana дополнительно важно:

- refresh runner: `ops/analytics_refresh.py`
- systemd units: `ops/systemd/amonora-analytics-refresh.{service,timer}`, `ops/systemd/amonora-grafana.service` и `ops/systemd/amonora-grafana-db-tunnel.service`
- provisioning root: `ops/grafana/`
- env template: [`ops/env/amonora-grafana.env.template`](/home/dextrmed/projects/amonora_bot/ops/env/amonora-grafana.env.template)
- tunnel env template: [`ops/env/amonora-grafana-db-tunnel.env.template`](/home/dextrmed/projects/amonora_bot/ops/env/amonora-grafana-db-tunnel.env.template)
- SQL template для read-only PostgreSQL user: [`ops/grafana/sql/grant_grafana_reader.sql.template`](/home/dextrmed/projects/amonora_bot/ops/grafana/sql/grant_grafana_reader.sql.template)
- canonical dashboards: `ops/grafana/dashboards/*.json`
- alert provisioning: `ops/grafana/provisioning/alerting/*.yaml`
- raw event retention: `180 days`
- dashboard refresh baseline: не чаще `5m`

### analytics / Grafana

Минимальный production rollout для analytics выглядит так:

1. применить schema changes обычным app startup path;
2. создать read-only PostgreSQL role по шаблону `ops/grafana/sql/grant_grafana_reader.sql.template`;
3. положить реальные значения в `/etc/amonora/grafana.env`;
4. установить `Grafana OSS` package на Estonia infra-host;
5. положить tunnel env в `/etc/amonora/grafana-db-tunnel.env` на Estonia и включить `amonora-grafana-db-tunnel.service`;
6. включить `amonora-grafana.service` на Estonia и `amonora-analytics-refresh.timer` на core;
7. для первого старта один раз прогнать `python -m ops.analytics_refresh --backfill --full-refresh` в off-peak окно;
8. после этого обычный timer должен идти без `--backfill` раз в `10 минут`.
9. положить одинаковый secret для `AMONORA_GRAFANA_ALERTS_WEBHOOK_SECRET` на core и для `GRAFANA_ALERTS_WEBHOOK_URL` на Estonia-side Grafana env;
10. после reload Grafana проверить, что dashboards и alert resources подхватились без ручного UI-save.

Базовый analytics event contract:

- attribution: `analytics_user_attribution` хранит `first_*` и `last_*` source для пользователя;
- event ledger: `analytics_events` хранит только low-volume business milestones, а не clickstream;
- rollups for Grafana: `analytics_daily_stage_counts`, `analytics_daily_revenue`, `analytics_daily_connection`, `analytics_daily_payment_failure_reasons`, `analytics_daily_attribution_integrity`, `analytics_cohort_retention`; compatibility tables `analytics_daily_stage_segments` and `analytics_daily_revenue_segments` may still exist in schema, but the strict suite should not depend on them for its core business panels;
- ops rollups for Grafana: `analytics_hourly_ops_incidents`, `analytics_hourly_ops_snapshots`, `analytics_runtime_status`;
- refresh cursor: `analytics_refresh_state`;
- Grafana panels и alert rules не должны ходить напрямую в `users`, `payment_records`, `vpn_client_activations`, `finance_entries`, `control_notification_events` или `channel_post_touches`.

Strict-suite expectations для Grafana:

- `Главная Amonora` должна оставаться коротким executive-обзором: KPI-strip, короткая воронка, `Сегодня / 7д / 30д`, свежесть данных, integrity и активные алерты без deep-dive таблиц;
- `Воронка роста` — канонический dashboard пути `канал -> бот -> подключение -> деньги`: использовать человекочитаемые шаги `Начало подключения / Готов к подключению`, но считать их через `onboarding_* OR connection_*`; показывать `Воронка подключения`, `Потери по этапам`, источник, payment-failure блок и data-integrity без лишних спорных метрик;
- `Источники и посты` и `Качество подключения` должны уметь drill-down по `source_key / start_param` без raw-table join-ов;
- `Выручка и монетизация` должна отдельно показывать `Новые оплаты`, `Продления`, `Выручка новых`, `Выручка продлений`, `Общая выручка`, а не смешивать первые активации и renewals в одну метрику;
- `Удержание и отток` должен читать `active_users` из `analytics_cohort_retention`, а не высчитывать его в panel-side SQL;
- `Алерты и инциденты` должен показывать `source_key_integrity`, дневной attribution-integrity слой и growth/revenue anomaly watch рядом с ops freshness.

Канонический suite на April 6, 2026:

- `Главная Amonora`
- `Воронка роста`
- `Источники и посты`
- `Выручка и монетизация`
- `Удержание и отток`
- `Качество подключения`
- `Операции и ремонты`
- `Алерты и инциденты`

Alert delivery contract:

- Grafana сама не пишет в Telegram;
- contact point отправляет grouped webhook payload на core route `/dashboard/api/internal/grafana/alerts/{secret}`;
- core normalizes payload и создаёт `ControlNotificationEvent` в уже существующем Telegram control contour;
- policy-grouping должен оставаться включённым, чтобы warning/critical сигналы не превращались в pager flood.
- Stage B alert rules должны жить в том же repo-managed provisioning и покрывать минимум: `bot_start -> config` conversion drop, `config -> payment` drop-off, `payment_started -> payment_success` conversion drop, `paid -> connected gap`, `source_key_integrity`.

## Подтверждённые rollout-заметки

По состоянию на 24 марта 2026 года дополнительно подтверждено:

- из WSL доступ к backend `46.21.81.186` надёжно проходит через Windows OpenSSH path, тогда как raw Linux `ssh` может не работать;
- backend host может аутентифицироваться в GitHub своим ключом `/home/ubuntu/.ssh/id_github_amonora`, поэтому при локальном блоке `git push` он может использоваться как GitHub bridge;
- live runtime tree остаётся `/opt/amonora_bot`;
- ранее ожидаемый `/opt/amonora_bot_git` сейчас отсутствует; на сервере присутствует fallback checkout `/opt/amonora_bot_git.preclean-20260322-065219`;
- на сервере уже есть следы archive-based rollout flow через `/opt/amonora-*.tgz` и `/opt/remote_deploy_*.sh`, поэтому current deploy reality нельзя считать простым `git pull` в live tree.

## Минимальный порядок проверки при инциденте

Если какой-то сервис не работает, минимальный порядок проверки такой:

1. Проверить, поднят ли процесс или `systemd` unit.
2. Проверить, слушает ли нужный внутренний порт.
3. Проверить `.env` и критичные токены.
4. Проверить доступ к PostgreSQL.
5. Проверить `nginx`, если проблема видна снаружи, а внутренний сервис жив.
6. Проверить логи конкретного сервиса.

## Что проверять по типу проблемы

### Если не открывается сайт

Проверить:

- `landing` на `127.0.0.1:8090`
- `/health`
- `nginx`
- SSL / reverse proxy

### Если не открывается админка

Проверить:

- `dashboard/ui` на `127.0.0.1:3001`
- `dashboard` на `127.0.0.1:8088`
- маршруты `nginx`
- auth endpoints

### Если не работает основной бот

Проверить:

- `amonora-bot.service`
- `BOT_TOKEN`
- PostgreSQL
- доступ к VPN API

### Если не работает test-бот

Проверить:

- `amonora-test-bot.service`
- `AMONORA_TEST_BOT_TOKEN`
- allowlist env для test-бота или fallback на `ADMIN_IDS`
- PostgreSQL
- что test VPN profiles на Germany / Denmark по-прежнему слушают `9443/10443`

### Если не работает Denmark MTProto proxy

Проверить:

- `amonora-dk-mtproxy.service`
- `/etc/mtproxy/proxy-secret`
- `/etc/mtproxy/proxy-multi.conf`
- `/etc/mtproxy/secret.hex`
- `11443/tcp` в `ufw`
- что `dk.amonoraconnect.com` по-прежнему резолвится напрямую в `81.17.159.58`, а не в сторонний proxy/CDN IP
- что `xray.service` всё ещё активен и не конфликтует по портам
- что shared `tg://proxy` ссылка не устарела после rotation секрета

### Если не работает support-бот

Проверить:

- `amonora-support-bot.service`
- `SUPPORT_BOT_TOKEN`
- PostgreSQL
- support storage / ticket flow

### Если не работают напоминания или watchdog

Проверить:

- соответствующий `.timer`
- соответствующий `.service`
- доступ к БД
- токены и env
- доступ core host `46.21.81.186` к `22/tcp` на managed VPN nodes; Germany и Estonia держат `ufw limit 22/tcp`, поэтому для мониторинга должен существовать отдельный allowlist для core IP, иначе `dashboard.services.get_server_snapshots()` падает в `SSH-мониторинг ноды недоступен`
- если SSH-мониторинг временно недоступен, но `xray / 3x-ui` control plane продолжает отвечать, это теперь считается monitoring gap, а не full node outage; spam `node_offline` в таком состоянии означает, что на хосте ещё крутится старый `ops/server_watchdog.py` без текущего фикса
- с 11 апреля 2026 года remote-node `ping` в dashboard/watchdog больше не должен измеряться через `22/tcp`: product health probe теперь обязан идти по публичным VPN listeners (`Germany 443`, `Denmark 443/8443`), иначе SSH brute-force noise на ноде будет выглядеть как ложная деградация runtime
- для Germany `Amonora Germany Primary` важно различать `3x-ui runtime` и `panel/tunnel` status: `xui_service_status` является source of truth для user-facing runtime health, а `xui_status` нужно трактовать как control-plane/panel seam; panel timeout сам по себе не должен открывать `node_offline`, пока `3x-ui` service на ноде активен

## Главные зависимости между сервисами

- `bot` зависит от `backend`, PostgreSQL и VPN-интеграции
- `support_bot` зависит от `backend` и PostgreSQL
- `dashboard` зависит от `backend`, PostgreSQL и support storage
- `control_bot` зависит от `backend`, PostgreSQL и части `dashboard.services`
- `amonora-access-reminders.service` зависит от `bot`, `control_bot.storage`, `dashboard.services`, PostgreSQL, локального `systemctl`, SSH-доступа к managed nodes и обоих bot tokens (`BOT_TOKEN`, `AMONORA_CONTROL_BOT_TOKEN`)
- `dashboard/ui` зависит от `dashboard`
- `landing` зависит от общей Python-логики, документации и части платёжного контура
- `ops` обслуживает запуск и связность всего runtime

## Важное правило

Если проблема непонятна, сначала нужно определить, это проблема:

- интерфейса;
- backend/API;
- базы данных;
- `nginx`/маршрутизации;
- фонового процесса;
- внешней интеграции.

Только после этого имеет смысл углубляться в конкретный модуль.
