# DOMAIN

## Сущности системы

| Сущность | Где хранится | Кто создаёт | Описание |
|----------|-------------|-------------|----------|
| **Пользователь** | PostgreSQL (`backend`) | `bot`, `landing` (bridge-user) | Клиент с trial/подпиской, устройствами, балансом, рефералами |
| **Подписка** | PostgreSQL | `bot`, `dashboard`, платёжный flow | Состояние trial или платного доступа |
| **Устройство** (`VpnClient`) | PostgreSQL (`backend`) | `bot`, `dashboard` | VPN-подключение: протокол, регион, ключ, QR |
| **Доп. слот устройства** (`DeviceSlotEntitlement`) | PostgreSQL | Платёжный контур | Временное +1 устройство до конца paid-периода |
| **Тариф** | Runtime-config + env | Команда через конфигурацию | Цена, срок, код тарифа |
| **Баланс** (`UserBalanceEvent`) | PostgreSQL | Рефералы, платёжный контур | RUB-кредит для оплаты подписок |
| **VPN-нода** (`ManagedServer`) | PostgreSQL + config | Команда / `dashboard` | Сервер, страна, протокол, статус |
| **Платёж** (`PaymentRecord`) | PostgreSQL | `bot`, `landing` webhook, `dashboard` | Оплата: Stars, Platega (СБП/крипто), ручная |
| **Тикет поддержки** (`SupportTicket`) | PostgreSQL | `support_bot`, клиент | Обращение + история сообщений |
| **Администратор** (`DashboardAdmin`) | PostgreSQL | Команда | Вход в админку, двухэтапная авторизация |
| **Системное уведомление** (`ControlNotificationEvent`) | PostgreSQL | `bot`, `dashboard`, `ops` | Typed-события для `@amonora_control_bot` |
| **PromoCode** | PostgreSQL (`backend.core`) | `dashboard` | Скидка / дни доступа / подарочная подписка |

## Дополнительные служебные сущности

| Сущность | Описание |
|----------|----------|
| `DashboardSession` | Сессии входа администраторов |
| `FinanceEntry` | Финансовые записи |
| `DashboardAuditLog` | Журнал админ-действий |
| `ControlAdminNotificationPreference` | Per-admin настройки уведомлений |
| `ControlMessageTemplate` | Шаблоны сообщений |
| `ControlBroadcastCampaign` | Кампании рассылок |
| `ControlTriggerRule` | DB-driven правила автотриггеров |
| `ControlTriggerDeliveryLog` | История доставок триггеров |

## Главные business rules

- Trial выдаётся один раз и привязан к подписке на канал
- Ручной платёж не даёт доступ до подтверждения
- `support_bot` не получает auth-коды, payment review, node alerts
- `dashboard/ui` не является источником бизнес-истины
- PromoCode / gift-коды обрабатываются через общий платёжный слой
