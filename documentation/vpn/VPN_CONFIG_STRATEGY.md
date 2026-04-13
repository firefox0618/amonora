# AMONORA CONNECT — VPN CONFIG STRATEGY
Дата: 21 марта 2026

## Цель

Держать VPN-контур менее детектируемым, более стабильным и более управляемым без ломки текущих пользователей и без насильственного перевода всего парка на один transport stack.

## Текущая стратегия нод

### Denmark

- роль: fast modern route
- runtime: standalone `Xray core`
- transport: `VLESS + Reality + XHTTP`
- public posture: co-primary route after validation
- product rollout: public route alongside Germany, with Germany preserved as the compatibility fallback

### Germany

- роль: stable compatibility route
- runtime: `3x-ui` / `XUIClient`
- transport model: текущий рабочий panel-backed контур
- public posture: co-primary route для совместимости и fallback

### Estonia

- роль: reserve / testing
- runtime: `3x-ui` / `XUIClient`
- public posture: не user-facing для обычного выбора

## Denmark golden profile

### Primary

- port: `443`
- camouflage family: `www.apple.com`
- path: `/api/v1/updates`
- XHTTP mode: `packet-up`
- ALPN:
  - `h3`
  - `h2`
  - `http/1.1`
- policy: `H3 preferred`, но не `H3 only`

### Reserve

- port: `8443`
- camouflage family: `www.apple.com`
- path: `/graphql`
- XHTTP mode: `packet-up`
- ALPN:
  - `h2`
  - `http/1.1`
- policy: reserve H2-friendly fallback

### Denmark runtime rules

- `loglevel = none`
- явный meta/source-of-truth:
  - `/usr/local/etc/xray/config.json`
  - `/usr/local/etc/xray/amonora_dk_meta.json`
- meta файл обязан хранить:
  - `active_profile`
  - `primary` / `reserve` profile data
  - usable client-side public key field
  - default Reality fingerprint (`chrome`)
  - distinct `shortId` values for primary and reserve
  - MTU policy
  - compatibility fallback region
  - DNS upstream policy:
    - `https+local://cloudflare-dns.com/dns-query`
    - `https+local://dns.sb/dns-query`
    - `localhost`

## Germany and Estonia policy

- `Germany` и `Estonia` остаются `3x-ui`-backed в этом проходе;
- fleet-wide transport migration на `XHTTP` не делается;
- persistence-safe hardening допускается только через:
  - `x-ui.db`
  - поддерживаемый runtime regen/restart
  - documented host-level baseline

## Fleet baseline

Для `DK`, `DE`, `EE` baseline должен быть таким:

- `BBR` включён
- `TCP Fast Open` включён и проверен
- увеличенные socket buffers для VPN-нагрузки
- `nofile = 65535`
- firewall policy нормализован
- torrent traffic заблокирован

## Torrent-block policy

### Denmark

- блокировка торрентов делается напрямую в standalone `Xray core` routing

### Germany and Estonia

- блокировка торрентов должна оставаться persistence-safe для `3x-ui`
- routing rule `protocol = bittorrent -> blocked` должен быть в генерируемом runtime
- для корректной работы detection на proxy-inbounds включается `sniffing.enabled` через `x-ui.db`, а не через ручной edit generated config

## Firewall policy

Публично допустимы только:

- `22/tcp`
- `443/tcp`
- `8443/tcp` только там, где реально нужен reserve/fallback

Дополнительно:

- `22/tcp` должен быть под rate limit
- panel ports `2053` / `2096` не должны быть доступны снаружи
- `8443/tcp` остаётся намеренно открытым на `Germany` и `Estonia`, пока там живут активные Trojan compatibility inbounds
- `80/tcp` не должен оставаться открытым без явной причины

## Official client packs

Официальные пакеты теперь обязательны как deliverable, а не как устная рекомендация.

Поддерживаемые targets:

- `v2rayNG`
- `Nekoray`
- `Streisand`

Набор паков:

- `Denmark preferred split tunnel`
- `Full-tunnel fallback`
- `Germany compatibility fallback profile`
- JSON import artifacts
- QR-code references for mobile onboarding
- text snippets with MTU and routing guidance

Артефакты лежат в:

- `documentation/vpn/CLIENT_PACK_POLICY.md`
- `documentation/vpn/client-packs/*`

## MTU policy

Для мобильных сетей:

- default: `1400`
- troubleshooting fallback: `1420`

Правила:

- `1500` не считается рекомендуемым default для mobile-heavy маршрутов
- если клиент умеет хранить MTU в profile/TUN, использовать `1400`
- если клиент не умеет импортировать MTU из профиля, это должно быть отдельным шагом в инструкции
- то же правило применяется и к `Germany` compatibility packs, отдельной `1500`-политики для них нет

## Split-tunnel policy

Recommended split-tunnel packs должны:

- вести `geoip:ru`, `geoip:private`, `geosite:category-ru`, `geosite:yandex`, `geosite:vk` напрямую
- вести blocked/global destinations через VPN
- блокировать `bittorrent`
- предпочитать `Denmark`, если клиент проходит compatibility matrix
- использовать Xray-compatible `routing.domainStrategy = IPIfNonMatch` и финальное правило `tcp,udp -> proxy`

Full-tunnel fallback:

- уводит весь трафик через VPN
- остаётся аварийным вариантом при сложных клиентских/сетевых кейсах

## Что не делать

- не ломать старые рабочие конфиги только ради унификации
- не включать `XHTTP/HTTP3` fleetwide на старых нодах без отдельного controlled rollout
- не редактировать generated `3x-ui` runtime JSON как primary persistence layer
- не делать `Denmark` broad default route, пока compatibility matrix не подтверждена

## Ожидаемый результат

- `Denmark` становится эталонной anti-DPI нодой
- `Germany` остаётся совместимым fallback-маршрутом
- `Estonia` остаётся reserve/testing
- client packs и MTU policy становятся частью официальной эксплуатационной модели
