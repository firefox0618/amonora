Дата: 2026-03-22
Сервер: Backend
Компонент: Bot / referral UI
Изменение: пользовательский экран `Реферальная система` временно отключён и заменён на placeholder `пока в разработке`
Причина: требуется убрать активную referral-поверхность из основного бота без изменения backend referral/balance логики
Риск: low
Проверка:
- `./venv/bin/python -m unittest -q tests.test_referral_ui tests.test_bot_copy_updates`
- в боте при открытии `🎁 Реферальная система` показывается placeholder
- callback `home:referrals` показывает тот же placeholder
Откат:
- вернуть предыдущие обработчики referral screen в `bot/handlers/referrals.py` и `bot/handlers/start.py`
- вернуть прежние тестовые ожидания и docs-описание referral screen
Статус: OK
