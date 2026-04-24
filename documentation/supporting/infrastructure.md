# Инфраструктура Amonora

> Supporting reference document. Use [ARCHITECTURE.md](/home/dextrmed/projects/amonora_bot/documentation/ARCHITECTURE.md), [RUNBOOK.md](/home/dextrmed/projects/amonora_bot/documentation/RUNBOOK.md) and the `documentation/ops/` layer as canonical current-state docs first.

## Текущая схема

После разделения инфраструктуры проект работает по схеме:

### Backend-сервер

IP: `46.21.81.186`
Публичный домен: `amonoraconnect.com`

На нём размещены:

- PostgreSQL
- основной Telegram-бот
- support-бот
- dashboard
- nginx
- SSH-туннель к `3x-ui` панели VPN-ноды

### Основная VPN-нода

IP: `213.108.20.34`
Публичный VPN-хост: `ffconnect.amonoraconnect.com`

На ней оставлены:

- `3x-ui`
- Docker / containerd
- SSH
- VPN-контур

### Дополнительная VPN-нода

IP: `185.88.37.71`
Публичный VPN-хост: `connect.amonoraconnect.com`

На ней оставлены:

- `AmneziaWG` (`awg-quick@awg0`)
- SSH
- VPN-контур

На VPN-сервере больше не должны жить:

- backend-боты
- дашборд
- PostgreSQL

Отдельное runtime-исключение:

- если Эстония repurpose-ится под публичный web-edge, на ней допускается только лёгкий `nginx` reverse-proxy слой для `amonoraconnect.com` / `www.amonoraconnect.com`, который проксирует web-запросы обратно на core `46.21.81.186`;
- это не делает Эстонию новым backend-host и не переносит туда боты, БД или dashboard runtime;
- такой ход нужен только как смена внешнего IP сайта, когда текущий web-entry на core плохо открывается в части сетей без VPN.

## Почему схема разделена

Это нужно по трём причинам:

1. Не смешивать веб-часть и VPN-нагрузку.
2. Упростить масштабирование backend и VPN по отдельности.
3. Снизить риск, что рост dashboard или ботов будет мешать VPN-сервису.

## Что считает дашборд

Сейчас дашборд должен видеть:

- локальный backend-сервер как `Amonora Core`
- основную немецкую VPN-ноду
- дополнительную эстонскую VPN-ноду

Для backend-сервера доступны полные live-метрики:

- CPU
- RAM
- Disk
- uptime
- ping
- текущая RX/TX скорость
- состояние systemd-сервисов

Для удалённых VPN-нод без отдельного агента доступна облегчённая схема:

- ping
- статусы, заданные в панели
- связка с `3x-ui`

## Доступ backend к 3x-ui

Панель `3x-ui` больше не должна быть публичной точкой интеграции для backend-сервисов.

Текущая рабочая схема:

- `3x-ui` живёт только на Germany VPN-нode;
- backend ходит к ним через постоянные SSH-туннели;
- `XUI_URL_DE` на backend: `http://127.0.0.1:12053`
- публичный `2053/tcp` наружу не открыт

После перевода Estonia на `AmneziaWG` 29 марта 2026 года:

- `XUI_URL_EE` и core-side `amonora-xui-tunnel-ee*` больше не являются актуальным runtime path;
- на Estonia не должно ожидаться наличие `3x-ui` panel API или `x-ui.db`;
- Estonia больше не рассматривается как хост для отдельных операторских сервисов и не является активной product VPN-нодой;
- текущий legacy VPN ingress на Estonia — только historical artifact, а не active product path.

Это нужно для того, чтобы логин панели и служебные запросы между backend и VPN не шли открытым HTTP через интернет.

## Что добавить позже

Чтобы получать полные live-метрики по удалённым нодам, позже лучше поставить лёгкий агент или отдельный metrics-collector.

Тогда для каждой VPN-ноды можно будет видеть:

- реальный CPU
- реальную RAM
- реальный Disk
- сетевую скорость по интерфейсу
- состояние inbound / outbound

## Базовые правила

- backend и VPN развиваются отдельно
- база данных живёт на backend-сервере
- все новые панели и внутренние сервисы поднимаются на backend-сервере или на отдельном admin-VPS, но не на VPN-ноде
