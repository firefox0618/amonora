# AMONORA — DASHBOARD TARGET STRUCTURE (IMPLEMENTATION MAP)

Дата: 19 марта 2026  
Цель: превратить vision панели в конкретную реализацию  
Формат: страница → блок → функции → действия → приоритет

---

# 0. ПРИНЦИП

Этот документ = **что конкретно делать в интерфейсе**

Не философия.  
Не стратегия.  
А:

- какие страницы
- какие блоки
- какие кнопки
- какие действия
- что делать сначала

---

# 1. DASHBOARD (ГЛАВНЫЙ ЭКРАН)

## Блок 1 — System Health
Показывать:
- backend
- DB
- bot
- Germany node
- Estonia node
- billing
- support

Кнопки:
- refresh
- open details

Приоритет: 🔴 CRITICAL

---

## Блок 2 — KPIs
- users total
- active users
- paid users
- devices
- revenue 30d
- pending payments
- open tickets

Приоритет: 🔴 CRITICAL

---

## Блок 3 — Requires Attention
- pending payments
- new tickets
- node degraded
- failed connections

Кнопки:
- open section

Приоритет: 🔴 CRITICAL

---

## Блок 4 — Activity Feed
- payments
- devices
- support actions

Приоритет: 🟠 HIGH

---

# 2. USERS

## Таблица
Поля:
- username
- status
- plan
- devices
- last payment

Функции:
- поиск
- фильтр

Приоритет: 🔴 CRITICAL

---

## User 360

Блоки:
- профиль
- устройства
- платежи
- support

Кнопки:
- продлить
- создать устройство
- удалить устройство

Приоритет: 🔴 CRITICAL

---

# 3. ACCESS

## Profiles
- список профилей

Кнопки:
- enable/disable
- mark legacy

---

## Devices
- все устройства

Кнопки:
- reissue
- delete

Приоритет: 🟠 HIGH

---

# 4. NODES

## Таблица
- страна
- статус
- CPU
- RAM
- users

Кнопки:
- refresh
- maintenance

Приоритет: 🔴 CRITICAL

---

## Детали ноды
- метрики
- нагрузка

---

# 5. PAYMENTS

## Таблица
- user
- amount
- status

Кнопки:
- confirm
- reject

Приоритет: 🔴 CRITICAL

---

# 6. SUPPORT

## Очередь
- new
- active
- closed

Кнопки:
- reply
- assign
- close

Приоритет: 🟠 HIGH

---

# 7. ALERTS

## Таблица
- severity
- message
- time

Кнопки:
- acknowledge
- open

Приоритет: 🟠 HIGH

---

# 8. SETTINGS

Разделы:
- тарифы
- env
- сервисы

Кнопки:
- save
- restart

Приоритет: 🟡 MEDIUM

---

# 9. AUDIT

## Таблица
- user
- action
- time

Приоритет: 🟡 MEDIUM

---

# 10. QUICK ACTIONS (ОБЯЗАТЕЛЬНО)

- найти пользователя
- подтвердить платеж
- открыть тикеты
- создать устройство

---

# 11. ЧТО ДЕЛАТЬ СЕЙЧАС (ПОРЯДОК)

## Шаг 1
- починить Users
- починить Payments
- починить Nodes

## Шаг 2
- собрать нормальный Dashboard

## Шаг 3
- сделать Access как отдельный раздел

## Шаг 4
- привести Support в порядок

## Шаг 5
- добавить Alerts

---

# 12. ЧТО НЕ ДЕЛАТЬ СЕЙЧАС

- не трогать AI
- не трогать Data
- не усложнять UI
- не делать “красиво” вместо “работает”

---

# 13. ФИНАЛ

Цель:

👉 сделать панель, где ты:
- видишь проблему
- понимаешь причину
- нажимаешь кнопку
- получаешь результат

Без хаоса.

---

# END
