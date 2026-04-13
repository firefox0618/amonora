# TASK 149 — Mobile mode public route result

Дата: 2 апреля 2026

## Что сделано

- `Мобильный` режим перестал быть admin-only в bot copy/availability layer;
- user-facing descriptions для режима обновлены: вместо текста "скоро появится" теперь объясняется сценарий сетей, где доступна только часть направлений;
- тесты bot copy обновлены под новое поведение;
- feature/public-state docs синхронизированы с новым user-facing статусом режима;
- production runtime должен хранить shared import-link только в env через `MOBILE_MODE_OVERRIDE_LINK_DE` / `MOBILE_MODE_OVERRIDE_LINK_DK`.

## Ожидаемый результат

- обычный пользователь может выбрать `Мобильный` режим в Germany и Denmark flows;
- бот больше не показывает устаревшую заглушку про подготовку режима при обычном выборе mobile route;
- shared import-link не появляется в git и меняется только через runtime env.
