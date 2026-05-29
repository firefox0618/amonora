# Client App

Контур клиентской публичной поверхности Amonora.

Целевое назначение:

- token-страницы подписки;
- публичный subscription feed;
- `summary/touch`;
- Happ wrapper;
- клиентский frontend bundle.

Текущее состояние:

- backend/runtime перенесён в `main.py` и `routes.py`;
- шаблоны лежат в `templates/`;
- собранная статика публикуется из `static/client-app/`;
- исходники frontend перенесены в `ui/`.

Совместимость:

- старый каталог `client_ui/` оставлен как thin wrapper для прежних `npm run build` / `npm run dev`;
- каноническая точка для frontend-кода теперь `apps/client/ui/`.
