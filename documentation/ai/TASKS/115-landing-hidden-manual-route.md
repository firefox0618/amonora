# TASK 115 — landing hidden manual route

## Status
Completed

## Goal
Вынести пользовательскую инструкцию из knowledge-поверхности панели на публичный landing как отдельную скрытую страницу `/manual`.

## Why
Пользовательская инструкция должна открываться по чистой внешней ссылке без захода в Панель управления и без новой кнопки в публичной навигации сайта.

## Context
Relevant docs and code areas:
- `documentation/PUBLIC_SURFACES.md`
- `documentation/FEATURES.md`
- `documentation/supporting/user-guide.md`
- `landing/main.py`
- `landing/templates/legal.html`

## Current behavior
Инструкция доступна через knowledge-маршрут панели по ссылке вида `/knowledge?doc=supporting%2Fuser-guide.md`.

## Desired behavior
Инструкция доступна и на лендинге по прямой ссылке `/manual`, при этом главная страница сайта не получает новую кнопку или ссылку на этот маршрут.

## Scope
Что включено в задачу:
- добавить скрытый маршрут `/manual` в `landing`
- использовать существующий markdown-файл как source of truth
- зафиксировать новую публичную поверхность в документации
- добавить минимальную smoke-проверку маршрута

## Out of scope
Что не меняется:
- knowledge-раздел панели
- содержание самой инструкции
- главная навигация лендинга

## Constraints
Important limitations:
- сохранить текущий markdown-файл как единый источник инструкции
- не добавлять кнопку `/manual` на главную
- не менять runtime paths существующих сервисов

## Risks
Potential regressions or sensitive areas:
- случайно продублировать контент в коде вместо чтения markdown
- случайно вывести `/manual` в публичную навигацию
- сломать layout существующих legal-страниц при обобщении шаблона

## Acceptance criteria
Concrete conditions for completion:
- `GET /manual` возвращает HTML-страницу с содержимым `documentation/supporting/user-guide.md`
- на главной лендинга нет ссылки на `/manual`
- legal-страницы продолжают использовать тот же шаблон

## Validation
Tests and manual checks required:
- `python -m unittest tests.test_landing_manual`
- вручную открыть `/manual` и убедиться, что страница читается как отдельный document page

## Deliverables
- code changes
- docs updates
- short implementation summary
