# Amonora Панель управления UI

Локальный `Next.js`-контур основного интерфейса панели управления Amonora.

## Что внутри

- `Next.js 16`
- `TypeScript`
- `Tailwind CSS`
- `TanStack Query`
- `Recharts`
- основной интерфейс панели поверх живого `FastAPI /dashboard/api/v2`

## Страницы

- `/overview`
- `/users`
- `/servers`
- `/traffic`
- `/payments`
- `/support`
- `/settings`

## Как это работает

`dashboard/ui` не содержит своей бизнес-логики.  
Он обращается к текущему backend через proxy route:

- frontend -> `/api/proxy/dashboard/api/v2/...`
- proxy -> `NEXT_PRIVATE_DASHBOARD_BACKEND`

По умолчанию backend ожидается на:

```env
NEXT_PRIVATE_DASHBOARD_BACKEND=http://127.0.0.1:8088
```

## Локальный запуск

1. Подними backend-дешборд локально на `127.0.0.1:8088`
2. Скопируй `.env.example` в `.env.local`
3. Запусти frontend:

```bash
npm install
npm run dev
```

По умолчанию UI откроется на:

- [http://127.0.0.1:3001](http://127.0.0.1:3001)

## Важный нюанс про WSL

Если запускать `Next.js` из Windows через путь вида `\\wsl$\\...`, `webpack/turbopack` может упираться в системные ограничения `readlink`.

Самый стабильный запуск для `dashboard/ui`:

- либо из терминала **внутри WSL**
- либо из проекта, лежащего на обычном Windows-диске

Код при этом уже проходит:

- `npm run typecheck`
- `npm run lint`

## Авторизация

Используется текущая схема Amonora:

- логин / пароль
- код в Telegram
- та же backend session model

## Статус

Это основной новый UI панели управления, встроенный внутрь общего контура `dashboard`.
