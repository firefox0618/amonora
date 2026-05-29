# Разделение `landing` на `site` и `client`

## Назначение

Этот документ фиксирует безопасную границу разделения текущего контура `landing/` без переноса кода.

Цель шага:

- понять, что в `landing/` относится к обычному сайту;
- понять, что относится к клиентской подписке;
- отдельно отметить маршруты и функции, которые вообще не должны оставаться в будущем `site`.

## Что найдено в `landing/`

### Код и входная точка

- `landing/main.py`

### Шаблоны

- `landing/templates/index.html`
- `landing/templates/legal.html`
- `landing/templates/client_subscription_shell.html`
- `landing/templates/client_happ_wrapper.html`

### Статика

- `landing/static/landing.css`
- `landing/static/landing.js`
- `landing/static/manual/...`
- `landing/static/client-app/...`
- остальные изображения и SVG для лендинга

## Главный вывод

Текущий `landing/` совмещает три роли:

1. обычный публичный сайт;
2. клиентскую поверхность подписки;
3. служебные и интеграционные endpoints, которые должны уйти из сайта в другие контуры.

То есть проблема не только в том, что надо разделить `site` и `client`.

Проблема глубже: внутри `landing/` уже находятся маршруты, которым в будущем не место ни в `site`, ни в чистом `client`.

## Что относится к будущему `site`

Это всё, что является витриной и публичным сайтом.

### Маршруты

- `GET /`
- `HEAD /`
- `GET /legal/{page_key}`
- `GET /manual`
- `GET /{filename}.txt`

### Шаблоны

- `templates/index.html`
- `templates/legal.html`

### Статика

К `site` относится обычная лендинговая статика:

- `static/landing.css`
- `static/landing.js`
- `static/manual/...`
- `static/amonora-logo.svg`
- `static/favicon.svg`
- `static/og-image.png`
- `static/sakura-*.svg`

### Ответственность

Будущий `site` должен отвечать только за:

- лендинг;
- юридические страницы;
- пользовательскую инструкцию;
- верификационные `.txt`-файлы;
- публичный визуальный контент.

## Что относится к будущему `client`

Это всё, что связано с публичной клиентской подпиской и клиентским веб-интерфейсом.

### Маршруты

- `GET /api/public/subscriptions/{token}/summary`
- `POST /api/public/subscriptions/{token}/touch`
- `GET /sub/{token}`
- `GET /happ/add`
- `GET /{token}`

### Шаблоны

- `templates/client_subscription_shell.html`
- `templates/client_happ_wrapper.html`

### Статика

- `static/client-app/...`
- mount `app.mount("/client-static", ...)`

### Ответственность

Будущий `client` должен отвечать за:

- страницу клиентской подписки;
- публичный feed;
- Happ wrapper;
- клиентские token-страницы;
- клиентский frontend bundle.

## Что не должно оставаться в будущем `site`

Ниже перечислены маршруты, которые сейчас живут в `landing`, но по смыслу не являются частью сайта.

### `GET /health`

Это служебный health endpoint.

Целевое место:

- остаётся как служебный endpoint приложения;
- не относится к пользовательскому контуру `site`;
- в будущем должен рассматриваться как инфраструктурная поверхность конкретного runtime-сервиса.

### `POST /bridge/access`

Сейчас этот маршрут:

- создаёт bridge-пользователя;
- создаёт временный доступ;
- выдаёт VPN-ключ;
- управляет rate limit и cookie;
- напрямую связан с provisioning.

Это не сайт.

Целевое место:

- либо `apps/vpn-service/` как endpoint выдачи мостового доступа;
- либо отдельный backend/core endpoint, который сайт вызывает как внешний API.

### `POST /vpn/activate`

Сейчас это legacy-endpoint с ответом `410 Gone`.

Целевое место:

- либо удалить позже как устаревший;
- либо временно держать вне `site` как legacy-совместимость.

### `POST /webhooks/crypto-pay/{secret}`

Это платежный webhook.

Целевое место:

- не `site`;
- не `client`;
- будущий контур платежей / core-api / payment integration.

### `POST /webhooks/platega/{secret}`

Это внешний webhook платёжного провайдера.

Целевое место:

- не `site`;
- не `client`;
- будущий контур платежей / core-api / payment integration.

## Предварительная карта разделения `landing`

### Часть 1. `apps/site`

Сюда должны перейти:

- лендинговые страницы;
- legal pages;
- manual page;
- verification txt;
- обычная публичная статика сайта.

### Часть 2. `apps/client`

Сюда должны перейти:

- client token page;
- public subscription summary;
- public subscription touch;
- subscription feed;
- Happ wrapper;
- client web bundle.

### Часть 3. Вынести из `landing` в отдельные контуры

Сюда относятся:

- `bridge/access`
- `webhooks/crypto-pay/...`
- `webhooks/platega/...`
- legacy `vpn/activate`

То есть при реальном разделении `landing` нужно не просто делить одну папку на две, а одновременно вычищать из неё сервисные и интеграционные обязанности.

## Что это значит для следующего этапа

Следующий безопасный шаг должен быть таким:

1. создать целевую файловую структуру для `site` и `client` без переноса логики;
2. подготовить границы импортов и entrypoint'ов;
3. отдельно отметить временные shared-части, которые пока останутся общими;
4. не переносить provisioning и webhooks в `site`.

## Итог

На текущем шаге перенос кода не выполнялся.

Зафиксировано:

- какие части `landing` являются сайтом;
- какие части `landing` являются клиентской подпиской;
- какие маршруты вообще не должны оставаться в будущем сайте.

## Статус после первого фактического переноса

Следующим практическим шагом часть файлов уже была физически перенесена в новые контуры, при этом публичные маршруты сохранены через текущий runtime `landing/main.py`.

### Уже перенесено в `apps/site`

- `index.html`
- `legal.html`
- обычная лендинговая статика;
- `manual/...`;
- изображения и SVG лендинга.

### Уже перенесено в `apps/client`

- `client_subscription_shell.html`
- `client_happ_wrapper.html`
- `static/client-app/...`

### Что пока осталось прежним

- текущий runtime всё ещё запускается через `landing/main.py`;
- публичные маршруты не менялись;
- разделение пока выполнено на уровне файловой структуры и путей к шаблонам/статике.
