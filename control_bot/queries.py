from __future__ import annotations

from collections import Counter
from datetime import timedelta
from html import escape
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from backend.core.database import async_session
from backend.core.models import ControlNotificationEvent, User
from bot.db import list_payment_records
from bot.utils.access import get_access_status_from_user, utcnow
from control_bot.access import (
    CONTROL_ROLE_ADMIN,
    CONTROL_ROLE_OPERATOR,
    CONTROL_ROLE_OWNER,
    control_role_allows,
    control_role_label,
    control_role_for_telegram_id,
)
from control_bot.dispatcher import CATEGORY_LABELS, event_payload, list_control_events
from control_bot.keyboards import control_menu_keyboard, control_secondary_keyboard
from control_bot.storage import (
    CTA_ACTIONS,
    CAMPAIGN_SCOPE_ADMIN,
    CAMPAIGN_SCOPE_TRIGGER,
    CAMPAIGN_SCOPE_USER,
    NOTIFICATION_CATEGORIES,
    get_broadcast_campaign,
    get_control_admin_profile,
    get_notification_preferences,
    get_trigger_rule,
    is_notification_category_mandatory,
    list_active_dashboard_sessions,
    list_control_admin_profiles,
    list_message_templates,
    list_notification_preference_rows,
    list_recent_broadcast_campaigns,
    list_trigger_rules_grouped,
    list_trigger_rules,
    segment_counts,
    serialize_campaign_metadata,
    serialize_template_buttons,
)
from dashboard.services import (
    get_payment_focus,
    get_server_snapshots,
    get_service_statuses,
    get_support_dashboard_counts,
    get_users,
    get_support_ticket_detail,
    get_user_detail,
    summarize_server_snapshots,
)
from dashboard.v2_data import (
    ACTIVE_ACCESS_STATUSES,
    get_v2_notifications_payload,
    get_v2_overview_payload,
    get_v2_servers_payload,
    get_v2_support_payload,
    get_v2_traffic_payload,
    get_v2_user_detail_payload,
    get_v2_users_payload,
)


SURFACE_SEP = "━━━━━━━━━━━━━━━━━━"
STATE_ICONS = {
    "healthy": "🟢",
    "warning": "🟡",
    "critical": "🔴",
    "unknown": "⚪",
}
SEVERITY_ICONS = {
    "INFO": "🔵",
    "WARNING": "🟡",
    "CRITICAL": "🔴",
}
EVENT_CATEGORY_ICONS = {
    "users": "👥",
    "access": "🔑",
    "nodes": "🌐",
    "payments": "💳",
    "support": "💬",
    "panel_auth": "🔐",
    "errors": "⚠️",
    "system": "🧾",
}

NODE_NAME_BY_CODE = {
    "de": "Германия",
    "ee": "Эстония",
    "dk": "Дания",
    "se": "Швеция",
}

NODE_NAME_ALIASES = {
    "germany": "Германия",
    "германия": "Германия",
    "europe": "Германия",
    "estonia": "Эстония",
    "эстония": "Эстония",
    "denmark": "Дания",
    "дания": "Дания",
    "sweden": "Швеция",
    "швеция": "Швеция",
}


def _sep() -> str:
    return SURFACE_SEP


def _fmt_dt(value) -> str:
    if value is None:
        return "—"
    return value.strftime("%Y-%m-%d %H:%M")


def _fmt_short_dt(value) -> str:
    if value is None:
        return "—"
    return value.strftime("%H:%M")


def _plural(value: int, one: str, few: str, many: str) -> str:
    value = abs(int(value))
    tail = value % 100
    if 11 <= tail <= 14:
        return many
    tail = value % 10
    if tail == 1:
        return one
    if 2 <= tail <= 4:
        return few
    return many


def _fmt_duration_minutes(minutes: int | None) -> str:
    total = max(int(minutes or 0), 0)
    hours = total // 60
    mins = total % 60
    return (
        f"{hours} {_plural(hours, 'час', 'часа', 'часов')}, "
        f"{mins} {_plural(mins, 'минута', 'минуты', 'минут')}"
    )


def _fmt_masked_telegram_id(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "—"
    if len(raw) < 4:
        return raw
    return f"{raw[:2]}••{raw[-2:]}"


def _node_name(value: Any, country_code: str | None = None) -> str:
    code = str(country_code or "").strip().lower()
    if code in NODE_NAME_BY_CODE:
        return NODE_NAME_BY_CODE[code]
    raw = str(value or "").strip()
    if not raw:
        return "—"
    lowered = raw.lower()
    if lowered in NODE_NAME_ALIASES:
        return NODE_NAME_ALIASES[lowered]
    if "germany" in lowered or "герман" in lowered or "europe" in lowered:
        return "Германия"
    if "estonia" in lowered or "эстон" in lowered:
        return "Эстония"
    if "denmark" in lowered or "дани" in lowered:
        return "Дания"
    if "sweden" in lowered or "швец" in lowered:
        return "Швеция"
    return raw


async def _telegram_ids_by_user_id(user_ids: set[int]) -> dict[int, int]:
    if not user_ids:
        return {}
    async with async_session() as session:
        rows = list(
            (
                await session.execute(
                    select(User.id, User.telegram_id).where(User.id.in_(sorted(user_ids)))
                )
            ).all()
        )
    return {int(user_id): int(telegram_id) for user_id, telegram_id in rows if telegram_id is not None}


async def _event_user_label_maps(events: list[ControlNotificationEvent]) -> tuple[dict[int, int], dict[int, str]]:
    user_ids: set[int] = set()
    labels: dict[int, str] = {}
    for item in events:
        payload = event_payload(item) if getattr(item, "payload_json", None) is not None else {}
        if payload.get("telegram_id"):
            labels[item.id] = str(payload["telegram_id"])
            continue
        user_id = payload.get("user_id")
        if user_id is not None:
            try:
                user_ids.add(int(user_id))
            except (TypeError, ValueError):
                continue
    telegram_map = await _telegram_ids_by_user_id(user_ids)
    return telegram_map, labels


def _payload_for_event(event: ControlNotificationEvent) -> dict[str, Any]:
    if getattr(event, "payload_json", None) is None:
        return {}
    return event_payload(event)


def _event_actor_label(
    event: ControlNotificationEvent,
    payload: dict[str, Any],
    telegram_by_user_id: dict[int, int],
    direct_labels: dict[int, str],
) -> str | None:
    direct = direct_labels.get(event.id)
    if direct:
        return direct
    user_id = payload.get("user_id")
    if user_id is not None:
        try:
            mapped = telegram_by_user_id.get(int(user_id))
        except (TypeError, ValueError):
            mapped = None
        if mapped is not None:
            return str(mapped)
    entity_id = str(event.entity_id or "").strip()
    if payload.get("telegram_id"):
        return str(payload["telegram_id"])
    if entity_id.isdigit() and len(entity_id) >= 6:
        return entity_id
    return None


def _label_for_payment_method(method: str) -> str:
    mapping = {
        "telegram_stars": "Telegram Stars",
        "sbp_manual": "СБП",
        "crypto_manual": "Крипта",
        "internal_balance": "Баланс",
    }
    return mapping.get(method, method)


def _status_badge(status: str) -> str:
    mapping = {
        "active": "🟢 active",
        "inactive": "🔴 inactive",
        "failed": "🔴 failed",
        "unknown": "⚪ unknown",
    }
    return mapping.get(status, status)


def _state_label(state: str) -> str:
    mapping = {
        "healthy": "healthy ✅",
        "warning": "warning ⚠️",
        "critical": "critical ⚠️",
        "unknown": "unknown",
    }
    return mapping.get(state, state)


def control_payment_keyboard(record_id: int, *, allow_review: bool = True, user_id: int | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if allow_review:
        rows.append(
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"control:payment:confirm:{record_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"control:payment:reject:{record_id}"),
            ]
        )
    if user_id is not None:
        rows.append([InlineKeyboardButton(text="👤 Открыть пользователя", callback_data=f"control:user:open:{user_id}")])
    rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"control:payment:open:{record_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def build_start_screen(telegram_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    role = control_role_for_telegram_id(telegram_id) or "unknown"
    profile = await get_control_admin_profile(telegram_id)
    name = profile.display_name if profile is not None else f"Admin {telegram_id}"
    overview = await get_v2_overview_payload()
    lines = [
        "🛰 <b>AMONORA CONTROL</b>",
        "",
        "Telegram-пульт команды Amonora для быстрых действий, алертов и реакции на инциденты.",
        "",
        _sep(),
        "👤 <b>ТВОЙ ПРОФИЛЬ</b>",
        _sep(),
        f"Имя: <b>{name}</b>",
        f"Telegram ID: <code>{telegram_id}</code>",
        f"Роль: <b>{control_role_label(role)}</b>",
        "",
        _sep(),
        "⚠️ <b>ТРЕБУЕТ ВНИМАНИЯ</b>",
        _sep(),
        f"Платежи на проверке: <b>{overview['system_alerts']['payments']['pending_confirmations']}</b>",
        f"Пользователи с repair-needed: <b>{overview['attention']['summary']['repair_needed']}</b>",
        f"Проблемные ноды: <b>{overview['system_alerts']['nodes']['issues']}</b>",
        f"Открытые обращения: <b>{overview['system_alerts']['support']['open_tickets']}</b>",
    ]
    lines.extend(["", "Выберите раздел кнопками ниже."])
    return "\n".join(lines), control_secondary_keyboard(role)


async def build_status_screen() -> tuple[str, InlineKeyboardMarkup | None]:
    services, snapshots, support_counts, unresolved_critical, payment_rows, traffic_payload = await _load_status_dependencies()
    snapshot_summary = summarize_server_snapshots(snapshots)
    service_states = Counter(item.get("status", "unknown") for item in services.values())
    total_services = len(services)
    active_services = service_states.get("active", 0)
    inactive_services = total_services - active_services
    peak_activity = max((item["activity"] for item in traffic_payload["peak_hours"]), default=0)
    current_activity = traffic_payload["peak_hours"][utcnow().hour]["activity"] if traffic_payload["peak_hours"] else 0
    lines = [
        "📊 <b>ДАШБОРД</b>",
        "",
        _sep(),
        f"🖥 <b>СЕРВИСЫ</b> ({active_services}/{total_services} ✅)",
        _sep(),
    ]
    for label, payload in services.items():
        del label
        status = payload.get("status", "unknown")
        lines.append(f"{payload.get('label', 'service')} — {_status_badge(status)}")
    lines.extend(
        [
            f"📊 Операционная активность: {current_activity} | Пик за 24ч: {peak_activity}",
            "",
            _sep(),
            (
                f"🌐 <b>НОДЫ</b> "
                f"(🟢 {snapshot_summary['total'] - snapshot_summary['critical'] - snapshot_summary['warning']} | "
                f"🟡 {snapshot_summary['warning']} | 🔴 {snapshot_summary['critical']})"
            ),
            _sep(),
        ]
    )
    for snapshot in snapshots:
        state = snapshot.get("overall_state", "unknown")
        icon = STATE_ICONS.get(state, "⚪")
        title = _node_name(snapshot.get("country_name") or snapshot.get("name"), snapshot.get("country_code"))
        lines.extend(
            [
                f"{icon} <b>{title}</b> — {_state_label(state)}",
                f"   📡 Пинг: {snapshot.get('ping_label', '—')}",
                f"   📈 Нагрузка: CPU {snapshot.get('cpu_percent', 0)}% | RAM {snapshot.get('memory_used_percent', 0)}% | Disk {snapshot.get('disk_used_percent', 0)}%",
                f"   🔑 Ключей: {int(snapshot.get('active_devices') or 0)} | Uptime: {snapshot.get('uptime', '—')}",
            ]
        )
    lines.extend(
        [
            "",
            _sep(),
            "📈 <b>ТРАФИК / TRANSFER</b>",
            _sep(),
            f"🌍 Текущий bandwidth: <b>{traffic_payload['overview']['current_bandwidth_label']}</b>",
            f"📦 Накопленный transfer: <b>{traffic_payload['overview']['total_transfer_gb']} GB</b>",
            "",
            _sep(),
            "💰 <b>ФИНАНСЫ / ЗАЯВКИ</b>",
            _sep(),
            f"📋 Support backlog: <b>{support_counts.get('new', 0) + support_counts.get('in_progress', 0)}</b>",
            f"💳 Ручные оплаты: <b>{len([row for row in payment_rows if row.payment_status == 'awaiting_admin_review'])}</b>",
            f"🚨 Активные CRITICAL alerts: <b>{len(unresolved_critical)}</b>",
            "",
            _sep(),
            "📊 <b>СИСТЕМНЫЕ МЕТРИКИ</b>",
            _sep(),
            f"💻 CPU (средний): <b>{snapshot_summary['avg_cpu']}%</b>",
            f"🧠 RAM (средняя): <b>{snapshot_summary['avg_memory']}%</b>",
            f"💾 Disk (средний): <b>{snapshot_summary['avg_disk']}%</b>",
            f"🌐 Servers reporting: <b>{traffic_payload['overview']['servers_reporting']}</b>",
            "",
            _sep(),
            f"📅 Обновлено: {_fmt_dt(utcnow())}",
        ]
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data="control:dashboard"),
                InlineKeyboardButton(text="🌍 Ноды", callback_data="control:nodes"),
            ],
            [
                InlineKeyboardButton(text="💳 Платежи", callback_data="control:payments"),
                InlineKeyboardButton(text="👥 Пользователи", callback_data="control:users"),
            ],
            [
                InlineKeyboardButton(text="⚠️ Проблемы", callback_data="control:problems"),
                InlineKeyboardButton(text="💬 Поддержка", callback_data="control:support"),
            ],
            [
                InlineKeyboardButton(text="🔐 Коды входа", callback_data="control:login_codes"),
                InlineKeyboardButton(text="⚙️ Уведомления", callback_data="control:notifications"),
            ],
        ]
    )
    return "\n".join(lines), keyboard


async def build_nodes_screen(filter_state: str | None = None) -> tuple[str, InlineKeyboardMarkup | None]:
    payload = await get_v2_servers_payload(force_refresh=True)
    snapshots = payload["nodes"]
    incidents = await list_control_events(category="nodes", unresolved_only=True, limit=50)
    incident_map = Counter(item.entity_id for item in incidents if item.entity_id)
    grouped: dict[str, list[dict[str, Any]]] = {"healthy": [], "warning": [], "critical": [], "unknown": []}
    for snapshot in snapshots:
        state = snapshot.get("overall_state") or "unknown"
        if state not in grouped:
            state = "unknown"
        grouped[state].append(snapshot)
    active_filter = filter_state if filter_state in {"critical", "warning", "healthy"} else None
    lines = ["🌍 <b>НОДЫ</b>", ""]
    sections = [active_filter] if active_filter else ["healthy", "warning", "critical"]
    titles = {
        "healthy": "🟢 <b>РАБОТАЮТ</b>",
        "warning": "🟡 <b>ПРЕДУПРЕЖДЕНИЯ</b>",
        "critical": "🔴 <b>КРИТИЧНЫЕ</b>",
    }
    for state in sections:
        items = grouped.get(state, [])
        lines.extend([_sep(), f"{titles[state]} ({len(items)})", _sep()])
        if not items:
            lines.append("✅ Нет нод в этом состоянии")
            continue
        for snapshot in items:
            title = _node_name(snapshot.get("country_name") or snapshot.get("name"), snapshot.get("country_code"))
            lines.extend(
                [
                    f"{STATE_ICONS.get(state, '⚪')} <b>{title}</b>",
                    f"   🟢 Статус: <b>{_state_label(snapshot.get('overall_state', 'unknown'))}</b>",
                    f"   🔑 Ключей: <code>{int(snapshot.get('active_devices') or 0)}</code>",
                    f"   🚨 Инцидентов: <code>{incident_map.get(str(snapshot.get('id')), 0)}</code>",
                    f"   ⚙️ Runtime: <code>{snapshot.get('xray_service_status') or snapshot.get('xui_status') or '—'}</code>",
                    f"   📡 Пинг: <code>{snapshot.get('ping_label', '—')}</code>",
                    f"   ⏱ Uptime: <code>{snapshot.get('uptime', '—')}</code>",
                ]
            )
    summary = summarize_server_snapshots(snapshots)
    lines.extend(
        [
            _sep(),
            f"📊 <b>ИТОГО:</b> {summary['total']} ноды | 🔴 {summary['critical']} critical | 🟡 {summary['warning']} warning | 🟢 {summary['total'] - summary['critical'] - summary['warning']} healthy",
        ]
    )
    keyboard_rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="🔄 Обновить", callback_data="control:nodes"),
            InlineKeyboardButton(text="🔴 Срочные", callback_data="control:nodes:critical"),
        ],
        [
            InlineKeyboardButton(text="🟡 Warning", callback_data="control:nodes:warning"),
        ],
    ]
    for snapshot in snapshots[:4]:
        keyboard_rows.append(
            [
                InlineKeyboardButton(
                    text=f"🖥 {str(_node_name(snapshot.get('country_name') or snapshot.get('name'), snapshot.get('country_code')))[:26]}",
                    callback_data=f"control:node:open:{int(snapshot['id'])}",
                )
            ]
        )
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    return "\n".join(lines), keyboard


async def build_node_focus(server_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    payload = await get_v2_servers_payload(server_id=server_id, force_refresh=True)
    node = payload.get("selected_node")
    if node is None or int(node.get("id") or 0) != int(server_id):
        return "Нода не найдена.", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🌍 Ноды", callback_data="control:nodes")]])
    lines = [
        "🖥 <b>НОДА</b>",
        "",
        f"Название: <b>{escape(str(node.get('name') or '—'))}</b>",
        f"Регион: <b>{escape(str(node.get('country_name') or '—'))}</b>",
        f"Статус: <b>{escape(str(node.get('status_label') or node.get('status') or '—'))}</b>",
        f"Хост: <code>{escape(str(node.get('host') or node.get('public_ip') or '—'))}</code>",
        f"CPU: <b>{int(node.get('cpu_percent') or 0)}%</b>",
        f"RAM: <b>{int(node.get('memory_used_percent') or 0)}%</b>",
        f"Disk: <b>{int(node.get('disk_used_percent') or 0)}%</b>",
        f"Throughput: <b>{escape(str(node.get('total_network_mbps') or 0))} Mbps</b>",
        f"Устройств: <b>{int(node.get('active_devices') or 0)}</b>",
        f"Heartbeat: <b>{escape(str(node.get('uptime') or '—'))}</b>",
    ]
    service_pills = node.get("service_pills") or []
    if service_pills:
        lines.extend(["", _sep(), "⚙️ <b>СЕРВИСЫ</b>", _sep()])
        for pill in service_pills[:6]:
            lines.append(f"• {escape(str(pill.get('label') or 'service'))}: <b>{escape(str(pill.get('value') or '—'))}</b>")
    rows = [
        [
            InlineKeyboardButton(text="🔄 Health check", callback_data=f"control:node:action:{server_id}:health_check"),
            InlineKeyboardButton(text="♻️ Restart", callback_data=f"control:node:action:{server_id}:restart"),
        ],
        [
            InlineKeyboardButton(text="🟡 Maintenance", callback_data=f"control:node:action:{server_id}:maintenance"),
            InlineKeyboardButton(text="🔄 Обновить статус", callback_data=f"control:node:action:{server_id}:refresh"),
        ],
        [InlineKeyboardButton(text="🌍 Назад к нодам", callback_data="control:nodes")],
    ]
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def build_payments_screen() -> tuple[str, InlineKeyboardMarkup | None]:
    return await build_payments_screen_for(None)


async def build_payments_screen_for(telegram_id: int | None) -> tuple[str, InlineKeyboardMarkup | None]:
    del telegram_id
    records = await list_payment_records()
    now = utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    review_records = [row for row in records if row.payment_status == "awaiting_admin_review"]
    today_success = [row for row in records if row.payment_status == "confirmed" and row.created_at >= today_start]
    week_success = [row for row in records if row.payment_status == "confirmed" and row.created_at >= week_start]
    today_refunds = [row for row in records if row.payment_status in {"rejected", "cancelled"} and row.created_at >= today_start]
    methods = Counter(_label_for_payment_method(row.payment_method) for row in today_success)
    lines = [
        "💳 <b>ПЛАТЕЖИ</b>",
        "",
        _sep(),
        "📋 <b>РУЧНЫЕ ОПЛАТЫ</b>",
        _sep(),
    ]
    if review_records:
        lines.append(f"🧾 На проверке: <b>{len(review_records)}</b>")
        for record in review_records[:5]:
            telegram_id = getattr(record, "telegram_id", None)
            tg_label = f"TG {_fmt_masked_telegram_id(telegram_id)}" if telegram_id else f"User {record.user_id or '—'}"
            lines.append(
                f"• #{record.id} — {tg_label} / {int(record.amount or 0)} {record.currency} / {_label_for_payment_method(record.payment_method)}"
            )
    else:
        lines.extend(["📭 Очередь пуста", "✅ Нет заявок на проверку"])
    lines.extend(
        [
            "",
            _sep(),
            "📊 <b>СТАТИСТИКА ЗА СЕГОДНЯ</b>",
            _sep(),
            f"💰 Успешных: <b>{len(today_success)}</b>",
            f"💸 Сумма: <b>{sum(int(row.amount or 0) for row in today_success)} ₽</b>",
            f"🔄 Возвратов / отклонений: <b>{len(today_refunds)}</b>",
            f"⏱ Средний чек: <b>{int(sum(int(row.amount or 0) for row in today_success) / len(today_success)) if today_success else 0} ₽</b>",
            "",
            _sep(),
            "📈 <b>СТАТИСТИКА ЗА НЕДЕЛЮ</b>",
            _sep(),
            f"💰 Всего: <b>{len(week_success)}</b> оплат",
            f"💸 Сумма: <b>{sum(int(row.amount or 0) for row in week_success)} ₽</b>",
            f"📊 Открытых заявок: <b>{len([row for row in records if row.payment_status in {'awaiting_admin_review', 'awaiting_user_payment'}])}</b>",
            "",
            _sep(),
            "💳 <b>СПОСОБЫ ОПЛАТЫ (сегодня)</b>",
            _sep(),
        ]
    )
    if methods:
        total_methods = sum(methods.values()) or 1
        for label, count in methods.most_common():
            percent = round((count / total_methods) * 100)
            lines.append(f"• {label}: {count} оплат ({percent}%)")
    else:
        lines.append("Сегодня успешных оплат ещё не было.")

    keyboard_rows: list[list[InlineKeyboardButton]] = [[InlineKeyboardButton(text="🔄 Обновить", callback_data="control:payments")]]
    for record in review_records[:6]:
        keyboard_rows.append(
            [
                InlineKeyboardButton(
                    text=f"💳 Заявка #{record.id}",
                    callback_data=f"control:payment:open:{record.id}",
                )
            ]
        )
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    return "\n".join(lines), keyboard


async def build_payment_focus(record_id: int, telegram_id: int | None = None) -> tuple[str, InlineKeyboardMarkup]:
    record = await get_payment_focus(record_id)
    if record is None:
        return "Заявка не найдена.", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Обновить", callback_data="control:payments")]])
    linked_user = None
    if record.get("user_id") is not None:
        try:
            linked_user = await get_v2_user_detail_payload(int(record["user_id"]))
        except Exception:
            linked_user = None
    text_lines = [
        f"💳 <b>ЗАЯВКА #{record_id}</b>",
        "",
        f"Telegram ID: <code>{record.get('telegram_id') or '—'}</code>",
        f"Username: <b>{escape(record.get('username') or '—')}</b>",
        f"Метод: <b>{_label_for_payment_method(record.get('payment_method') or '')}</b>",
        f"Статус: <b>{escape(str(record.get('payment_status') or '—'))}</b>",
        f"Полная стоимость: <b>{int(record.get('list_price_amount') or record.get('amount') or 0)} {escape(str(record.get('currency') or 'RUB'))}</b>",
        f"К оплате деньгами: <b>{int(record.get('amount') or 0)} {escape(str(record.get('currency') or 'RUB'))}</b>",
        f"Баланс: <b>{int(record.get('balance_applied_amount') or record.get('balance_reserved_amount') or 0)} {escape(str(record.get('currency') or 'RUB'))}</b>",
        f"Тариф: <b>{escape(str(record.get('tariff_label') or record.get('tariff_code') or '—'))}</b>",
    ]
    if record.get("reference"):
        text_lines.append(f"Референс: <code>{escape(str(record.get('reference')))}</code>")
    if record.get("note"):
        text_lines.append(f"Комментарий: <b>{escape(str(record.get('note')))}</b>")
    if linked_user is not None:
        text_lines.extend(
            [
                "",
                _sep(),
                "👤 <b>ПОЛЬЗОВАТЕЛЬ</b>",
                _sep(),
                f"Статус доступа: <b>{escape(str(linked_user['user']['status_label']))}</b>",
                f"Тариф: <b>{escape(str(linked_user['user']['plan_label']))}</b>",
                f"Устройств: <b>{len(linked_user.get('devices', []))}/{int(linked_user['user'].get('max_devices') or 3)}</b>",
                f"Доступ до: <b>{escape(str(linked_user['user']['access_expires_at']))}</b>",
            ]
        )
        if linked_user.get("vpn_repair_state", {}).get("repair_needed"):
            text_lines.append(
                f"⚠️ Repair needed: <b>{escape(str(linked_user['vpn_repair_state'].get('reason_label') or 'да'))}</b>"
            )
    text = "\n".join(text_lines)
    role = control_role_for_telegram_id(telegram_id) if telegram_id is not None else None
    return text, control_payment_keyboard(
        record_id,
        allow_review=record.get("payment_status") == "awaiting_admin_review" and control_role_allows(role, CONTROL_ROLE_OPERATOR),
        user_id=record.get("user_id"),
    )


async def build_users_screen() -> tuple[str, InlineKeyboardMarkup | None]:
    payload = await get_v2_users_payload()
    items = payload["items"]
    summary = payload["summary"]
    issue_rows = [
        row for row in items if row.get("status_state") in {"sync_error", "repair_needed", "awaiting_payment", "no_access"}
    ][:6]
    lines = [
        "👤 <b>ПОЛЬЗОВАТЕЛИ</b>",
        "",
        _sep(),
        "📊 <b>ОБЩИЙ СРЕЗ</b>",
        _sep(),
        f"Всего: <b>{summary['total']}</b>",
        f"Активные: <b>{summary['active']}</b>",
        f"Пробные: <b>{summary['trial']}</b>",
        f"Без доступа: <b>{summary['no_access']}</b>",
        f"Ожидают оплату: <b>{summary['waiting_payment']}</b>",
        f"Требуют ремонта: <b>{summary['needs_repair']}</b>",
        "",
        _sep(),
        "🔎 <b>ПОИСК</b>",
        _sep(),
        "Используй команду <code>/user 123</code>, <code>/user @username</code> или <code>/user telegram_id</code>.",
        "",
        _sep(),
        "⚠️ <b>ТРЕБУЮТ ВНИМАНИЯ</b>",
        _sep(),
    ]
    if issue_rows:
        for row in issue_rows:
            lines.append(
                f"• <b>{escape(str(row['username']))}</b> — {escape(str(row['status_label']))} · устройств {int(row['devices'])}/{int(row.get('max_devices') or 3)}"
            )
    else:
        lines.append("✅ Критичных пользовательских проблем сейчас не видно.")

    keyboard_rows: list[list[InlineKeyboardButton]] = [[InlineKeyboardButton(text="🔄 Обновить", callback_data="control:users")]]
    for row in issue_rows[:4]:
        keyboard_rows.append(
            [
                InlineKeyboardButton(
                    text=f"👤 {str(row['username'])[:24]}",
                    callback_data=f"control:user:open:{int(row['id'])}",
                )
            ]
        )
    keyboard_rows.append(
        [
            InlineKeyboardButton(text="⚠️ Проблемы", callback_data="control:problems"),
            InlineKeyboardButton(text="🧾 События", callback_data="control:events:users"),
        ]
    )
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


async def find_user_candidates(query: str) -> list[dict]:
    needle = str(query or "").strip().lstrip("@")
    if not needle:
        return []
    payload = await get_v2_users_payload(needle)
    items = payload["items"]
    lowered = needle.lower()
    exact: list[dict] = []
    for row in items:
        username = str(row.get("username") or "").strip().lstrip("@").lower()
        telegram_id = str(row.get("telegram_id") or "").strip()
        internal_id = str(row.get("id") or "").strip()
        if lowered in {username, telegram_id, internal_id}:
            exact.append(row)
    return exact or items[:8]


async def build_user_search_screen(query: str) -> tuple[str, InlineKeyboardMarkup | None]:
    candidates = await find_user_candidates(query)
    if not candidates:
        return (
            "👤 <b>ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН</b>\n\nПопробуй <code>/user 123</code>, <code>/user @username</code> или <code>/user telegram_id</code>.",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👤 Пользователи", callback_data="control:users")]]),
        )
    if len(candidates) == 1:
        return await build_user_focus(int(candidates[0]["id"]))

    lines = [
        "👤 <b>НАЙДЕНО НЕСКОЛЬКО ПОЛЬЗОВАТЕЛЕЙ</b>",
        "",
        f"Запрос: <code>{escape(query)}</code>",
        "",
    ]
    rows: list[list[InlineKeyboardButton]] = []
    for row in candidates[:8]:
        lines.append(
            f"• <b>{escape(str(row['username']))}</b> — TG <code>{row['telegram_id']}</code> · {escape(str(row['status_label']))}"
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"👤 {str(row['username'])[:24]}",
                    callback_data=f"control:user:open:{int(row['id'])}",
                )
            ]
        )
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def build_user_focus(user_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    payload = await get_v2_user_detail_payload(user_id)
    if payload is None:
        return "Пользователь не найден.", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👤 Пользователи", callback_data="control:users")]])
    user = payload["user"]
    devices = payload.get("devices", [])
    support_ticket = payload.get("support_ticket")
    payments = payload.get("payments", [])
    lines = [
        "👤 <b>КАРТОЧКА ПОЛЬЗОВАТЕЛЯ</b>",
        "",
        f"Username: <b>{escape(str(user['username']))}</b>",
        f"Telegram ID: <code>{user['telegram_id']}</code>",
        f"Внутренний ID: <code>{user['id']}</code>",
        f"Статус: <b>{escape(str(user['status_label']))}</b>",
        f"Тариф: <b>{escape(str(user['plan_label']))}</b>",
        f"Доступ до: <b>{escape(str(user['access_expires_at']))}</b>",
        f"Устройства: <b>{len(devices)}/{int(user.get('max_devices') or 3)}</b>",
        f"Протокол: <b>{escape(str(user['preferred_protocol']))}</b>",
    ]
    if payload.get("vpn_repair_state", {}).get("repair_needed"):
        lines.append(
            f"⚠️ Repair needed: <b>{escape(str(payload['vpn_repair_state'].get('reason_label') or 'да'))}</b>"
        )
    if devices:
        lines.extend(["", _sep(), "📱 <b>УСТРОЙСТВА</b>", _sep()])
        for device in devices[:5]:
            meta = device.get("metadata", {})
            lines.append(
                f"• <b>{escape(str(meta.get('device_name') or device.get('protocol') or 'device'))}</b> · "
                f"{escape(str(meta.get('device_type') or 'other'))} · "
                f"{escape(str(meta.get('node_label') or '—'))}"
            )
    if payments:
        latest_payment = payments[0]
        lines.extend(
            [
                "",
                _sep(),
                "💳 <b>ПОСЛЕДНИЙ ПЛАТЁЖ</b>",
                _sep(),
                f"#{latest_payment['id']} · {escape(str(latest_payment['payment_status_label']))} · {int(latest_payment['amount'])} {escape(str(latest_payment['currency']))}",
            ]
        )
    if support_ticket is not None:
        lines.extend(
            [
                "",
                _sep(),
                "💬 <b>ПОДДЕРЖКА</b>",
                _sep(),
                f"Статус: <b>{escape(str(support_ticket.get('status_label') or support_ticket.get('status') or '—'))}</b>",
                f"Обновлено: <b>{escape(str(support_ticket.get('updated_at_label') or '—'))}</b>",
            ]
        )

    can_grant_trial = not bool(user.get("trial_used")) and user.get("status") not in ACTIVE_ACCESS_STATUSES
    is_blocked = bool(user.get("is_blocked"))
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="🔄 Sync", callback_data=f"control:user:sync:{user_id}"),
            InlineKeyboardButton(text="🛠 Deep repair", callback_data=f"control:user:repair:{user_id}"),
        ],
        [
            InlineKeyboardButton(text="📅 Продлить 30 дней", callback_data=f"control:user:extend30:{user_id}"),
            InlineKeyboardButton(text="🎁 Выдать trial", callback_data=f"control:user:trial:{user_id}"),
        ],
        [
            InlineKeyboardButton(text="🔒 Блок" if not is_blocked else "🔓 Разблок", callback_data=f"control:user:{'block' if not is_blocked else 'unblock'}:{user_id}"),
            InlineKeyboardButton(text="🚫 Снять доступ", callback_data=f"control:user:clear:{user_id}"),
        ],
    ]
    if not can_grant_trial:
        rows[1][1] = InlineKeyboardButton(text="🎁 Trial недоступен", callback_data=f"control:user:noop:{user_id}")
    extra_row: list[InlineKeyboardButton] = []
    if support_ticket is not None:
        extra_row.append(InlineKeyboardButton(text="💬 Открыть поддержку", callback_data=f"control:support:open:{int(user['telegram_id']) if user.get('telegram_id') else user_id}"))
    if payments:
        extra_row.append(InlineKeyboardButton(text="💳 Последний платёж", callback_data=f"control:payment:open:{int(payments[0]['id'])}"))
    if extra_row:
        rows.append(extra_row)
    rows.append([InlineKeyboardButton(text="👥 Назад к пользователям", callback_data="control:users")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def build_alerts_screen(filter_severity: str | None = None, *, history: bool = False) -> tuple[str, InlineKeyboardMarkup | None]:
    severities = {filter_severity} if filter_severity in {"CRITICAL", "WARNING", "INFO"} else {"CRITICAL", "WARNING", "INFO"}
    unresolved = await list_control_events(severities=severities, unresolved_only=not history, limit=20)
    recent_history = await list_control_events(severities=severities, unresolved_only=False, limit=30)
    history_rows = [item for item in recent_history if item.resolved_at is not None][:5]
    critical_count = len([item for item in unresolved if item.severity == "CRITICAL"])
    warning_count = len([item for item in unresolved if item.severity == "WARNING"])
    info_count = len([item for item in unresolved if item.severity == "INFO"])
    resolved_durations: list[int] = []
    for item in history_rows:
        if item.resolved_at is not None:
            resolved_durations.append(int((item.resolved_at - item.created_at).total_seconds() // 60))
    avg_resolution = int(sum(resolved_durations) / len(resolved_durations)) if resolved_durations else 0
    lines = ["⚠️ <b>ОШИБКИ И ПРЕДУПРЕЖДЕНИЯ</b>", ""]
    for severity in ["CRITICAL", "WARNING", "INFO"]:
        rows = [item for item in unresolved if item.severity == severity]
        lines.extend([_sep(), f"{SEVERITY_ICONS[severity]} <b>{severity}</b> ({len(rows)})", _sep()])
        if rows:
            for item in rows[:5]:
                lines.extend(
                    [
                        f"{EVENT_CATEGORY_ICONS.get(item.category, '•')} <b>{item.title}</b>",
                        f"   └─ Категория: {CATEGORY_LABELS.get(item.category, item.category)}",
                        f"   └─ Время: {_fmt_dt(item.created_at)}",
                        f"   └─ Статус: {'active' if item.resolved_at is None else 'resolved'}",
                    ]
                )
        else:
            lines.append("✅ Нет уведомлений")
    lines.extend(
        [
            "",
            _sep(),
            "📜 <b>ИСТОРИЯ ИНЦИДЕНТОВ</b>",
            _sep(),
        ]
    )
    if history_rows:
        for item in history_rows:
            duration = int((item.resolved_at - item.created_at).total_seconds() // 60) if item.resolved_at else 0
            icon = "🟢" if item.resolved_at else SEVERITY_ICONS.get(item.severity, "•")
            lines.append(f"{icon} {_fmt_short_dt(item.created_at)} — {item.title} ({_fmt_duration_minutes(duration)})")
    else:
        lines.append("История пока пуста.")
    lines.extend(
        [
            "",
            _sep(),
            "📊 <b>СТАТИСТИКА</b>",
            _sep(),
            f"🔴 Critical: {critical_count}",
            f"🟡 Warning: {warning_count}",
            f"🔵 Info: {info_count}",
            f"⏱ Среднее время решения: { _fmt_duration_minutes(avg_resolution) }",
            "",
            _sep(),
            f"📅 Обновлено: {_fmt_dt(utcnow())}",
        ]
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data="control:alerts"),
                InlineKeyboardButton(text="🔴 Critical", callback_data="control:alerts:CRITICAL"),
            ],
            [
                InlineKeyboardButton(text="🟡 Warning", callback_data="control:alerts:WARNING"),
                InlineKeyboardButton(text="🔵 Info", callback_data="control:alerts:INFO"),
            ],
            [InlineKeyboardButton(text="📋 История", callback_data="control:alerts:history")],
        ]
    )
    return "\n".join(lines), keyboard


async def build_problems_screen() -> tuple[str, InlineKeyboardMarkup | None]:
    overview = await get_v2_overview_payload()
    payment_alert = overview["system_alerts"]["payments"]
    support_alert = overview["system_alerts"]["support"]
    node_alert = overview["system_alerts"]["nodes"]
    repair_attention = overview["attention"]
    lines = [
        "⚠️ <b>ПРОБЛЕМЫ / ТРЕБУЕТ ВНИМАНИЯ</b>",
        "",
        _sep(),
        "💳 <b>ПЛАТЕЖИ</b>",
        _sep(),
        f"На проверке: <b>{payment_alert['pending_confirmations']}</b>",
        f"Зависшие: <b>{payment_alert['stale_pending_confirmations']}</b>",
        "",
        _sep(),
        "👤 <b>ДОСТУП / REPAIR</b>",
        _sep(),
        f"Требуют ремонта: <b>{repair_attention['summary']['repair_needed']}</b>",
        f"Sync errors: <b>{repair_attention['summary']['sync_errors']}</b>",
        f"Высокий приоритет: <b>{repair_attention['summary']['high_priority_repairs']}</b>",
        "",
        _sep(),
        "💬 <b>ПОДДЕРЖКА</b>",
        _sep(),
        f"Открытые обращения: <b>{support_alert['open_tickets']}</b>",
        f"Новые: <b>{support_alert['new_tickets']}</b>",
        "",
        _sep(),
        "🖥 <b>НОДЫ</b>",
        _sep(),
        f"Проблемных: <b>{node_alert['issues']}</b>",
        f"Down: <b>{node_alert['down']}</b>",
        f"Degraded: <b>{node_alert['degraded']}</b>",
    ]
    keyboard_rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="💳 Платежи", callback_data="control:payments"),
            InlineKeyboardButton(text="💬 Поддержка", callback_data="control:support"),
        ],
        [
            InlineKeyboardButton(text="🌍 Ноды", callback_data="control:nodes"),
            InlineKeyboardButton(text="👥 Пользователи", callback_data="control:users"),
        ],
    ]
    for item in payment_alert.get("oldest_pending_manual_payments", [])[:2]:
        keyboard_rows.append([InlineKeyboardButton(text=f"💳 Платёж #{int(item['payment_id'])}", callback_data=f"control:payment:open:{int(item['payment_id'])}")])
    for item in repair_attention.get("repair_needed_users", [])[:2]:
        keyboard_rows.append([InlineKeyboardButton(text=f"👤 {str(item['username'])[:24]}", callback_data=f"control:user:open:{int(item['user_id'])}")])
    for item in support_alert.get("oldest_open_tickets", [])[:2]:
        keyboard_rows.append([InlineKeyboardButton(text=f"💬 Тикет {str(item['label'])[:24]}", callback_data=f"control:support:open:{int(item['ticket_user_id'])}")])
    for item in node_alert.get("items", [])[:2]:
        keyboard_rows.append([InlineKeyboardButton(text=f"🖥 {str(item['name'])[:24]}", callback_data=f"control:node:open:{int(item['server_id'])}")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


async def build_login_codes_screen(telegram_id: int | None = None) -> tuple[str, InlineKeyboardMarkup | None]:
    sessions = await list_active_dashboard_sessions()
    active_sessions = [row for row in sessions if row["ttl_minutes"] > 0]
    try:
        code_events = await list_control_events(category="panel_auth", limit=8)
    except Exception:
        code_events = []
    lines = ["🔐 <b>КОДЫ ВХОДА И СЕССИИ</b>", ""]
    lines.extend([_sep(), "🔐 <b>ПОСЛЕДНИЕ КОДЫ</b>", _sep()])
    if code_events:
        for event in code_events[:5]:
            payload = _payload_for_event(event)
            lines.append(
                f"• {_fmt_short_dt(event.created_at)} — <b>{escape(str(payload.get('admin_username') or 'admin'))}</b> "
                f"· код <code>{escape(str(payload.get('masked_code') or '••••••'))}</code> "
                f"· TTL {int(payload.get('ttl_minutes') or 0)} мин"
            )
    else:
        lines.append("Коды входа пока не отправлялись.")
    lines.extend(["", _sep(), "🧾 <b>АКТИВНЫЕ СЕССИИ</b>", _sep()])
    if active_sessions:
        for row in active_sessions[:8]:
            lines.append(
                f"• {escape(row['username'])} — {_fmt_masked_telegram_id(row.get('telegram_id'))} / {_fmt_dt(row['created_at'])} / TTL {int(row['ttl_minutes'])} мин"
            )
    else:
        lines.append("✅ Активных dashboard-сессий сейчас нет")
    keyboard_rows: list[list[InlineKeyboardButton]] = []
    if control_role_for_telegram_id(telegram_id or 0) == CONTROL_ROLE_OWNER:
        keyboard_rows.append([InlineKeyboardButton(text="🔒 Завершить все", callback_data="control:login_codes:terminate")])
    keyboard_rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="control:login_codes")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows) if keyboard_rows else None
    return "\n".join(lines), keyboard


async def build_help_screen(telegram_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    role = control_role_for_telegram_id(telegram_id) or "unknown"
    lines = [
        f"❔ <b>AMONORA CONTROL</b> — <code>{control_role_label(role)}</code>",
        "",
        _sep(),
        "📊 /status     — дашборд и системный срез",
        "📊 /dashboard  — тот же дашборд",
        "🌐 /nodes      — ноды и инфраструктура",
        "⚠️ /problems   — платежи / repair / support / nodes",
        "💳 /payments   — очередь оплат и review",
        "👥 /users      — обзор по пользователям",
        "👤 /user 123   — найти и открыть карточку пользователя",
        "💬 /support    — обращения поддержки",
        "🔐 /login_codes — коды входа и активные сессии",
        "⚙️ /notifications — уведомления по категориям",
        "🧾 /events     — последние события",
        "⚙️ /settings   — алиас уведомлений",
        "❔ /help       — эта справка",
        _sep(),
        "📣 Перешлите сюда пост из канала и следом отправьте кнопки в формате <code>Текст | URL</code>",
        "   две или три кнопки в одном ряду можно разделить через <code>||</code>",
        "   чтобы убрать кнопки у выбранного поста, отправьте <code>очистить</code>",
        _sep(),
    ]
    command_sep_index = lines.index(_sep(), 3)
    if control_role_allows(role, CONTROL_ROLE_ADMIN):
        lines.insert(command_sep_index, "📣 /channel   — owner/admin контент-план канала")
    if role == CONTROL_ROLE_OWNER:
        lines.insert(command_sep_index, "📢 /broadcast  — owner-only рассылки и триггеры")
        lines.append("🔐 <b>Owner-only:</b> terminate all sessions, broadcast/triggers, критичные owner-действия")
    else:
        lines.append("🔐 Owner-only блоки скрыты для твоей роли.")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ Уведомления", callback_data="control:notifications")]
        ]
    )
    return "\n".join(lines), keyboard


async def build_last_events_screen(
    category_filter: str | None = None,
    severity_filter: str | None = None,
) -> tuple[str, InlineKeyboardMarkup | None]:
    events = await list_control_events(limit=30)
    if category_filter in CATEGORY_LABELS:
        events = [item for item in events if item.category == category_filter]
    if severity_filter in {"CRITICAL", "WARNING", "INFO"}:
        events = [item for item in events if item.severity == severity_filter]
    day_cutoff = utcnow() - timedelta(hours=24)
    events = [item for item in events if item.created_at >= day_cutoff][:12]
    telegram_by_user_id, direct_labels = await _event_user_label_maps(events)
    lines = ["🧾 <b>СОБЫТИЯ</b> — <code>за сутки</code>", "", _sep()]
    if events:
        for item in events:
            icon = EVENT_CATEGORY_ICONS.get(item.category, "•")
            severity = " ‼️" if item.severity == "CRITICAL" else ""
            payload = _payload_for_event(item)
            line = f"{_fmt_short_dt(item.created_at)} {icon} {item.title}{severity}"
            if item.category in {"users", "access"}:
                actor = _event_actor_label(item, payload, telegram_by_user_id, direct_labels)
                if actor:
                    line += f" — <code>{actor}</code>"
            elif item.category == "nodes":
                node_name = _node_name(payload.get("country_name"), payload.get("country_code"))
                if node_name != "—" and node_name not in item.title:
                    line += f" — {node_name}"
            request_id = str(payload.get("request_id") or "").strip()
            if request_id:
                line += f" · req <code>{escape(request_id[:8])}</code>"
            lines.append(line)
    else:
        lines.append("За последние сутки событий пока нет.")
    critical_count = sum(1 for item in events if item.severity == "CRITICAL")
    info_count = sum(1 for item in events if item.severity == "INFO")
    lines.extend([_sep(), f"🔴 {critical_count} критическое | {info_count} информационных"])
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data="control:events"),
                InlineKeyboardButton(text="🔴 Critical", callback_data="control:events:critical"),
            ],
            [
                InlineKeyboardButton(text="🔑 Ключи", callback_data="control:events:access"),
                InlineKeyboardButton(text="👥 Пользователи", callback_data="control:events:users"),
            ],
            [
                InlineKeyboardButton(text="🌐 Ноды", callback_data="control:events:nodes"),
                InlineKeyboardButton(text="📊 Все события", callback_data="control:events"),
            ],
            [
                InlineKeyboardButton(text="💬 Поддержка", callback_data="control:events:support"),
                InlineKeyboardButton(text="🔐 Безопасность", callback_data="control:events:panel_auth"),
            ],
        ]
    )
    return "\n".join(lines), keyboard


async def build_support_screen(filter_mode: str = "all") -> tuple[str, InlineKeyboardMarkup | None]:
    payload = await get_v2_support_payload(filter_mode=filter_mode)
    tickets = payload["tickets"]
    counts = payload["counts"]
    visible_limit = 5
    filter_label = {
        "all": "Все",
        "new": "Новые",
        "in_progress": "В работе",
        "mine": "На мне",
        "closed": "Закрытые",
    }.get(filter_mode, "Все")
    lines = [
        "💬 <b>ПОДДЕРЖКА</b>",
        "",
        _sep(),
        f"Фильтр: <b>{filter_label}</b>",
        _sep(),
        f"Всего: <b>{int(counts.get('all', 0))}</b>",
        f"Новые: <b>{int(counts.get('new', 0))}</b>",
        f"В работе: <b>{int(counts.get('in_progress', 0))}</b>",
        f"На мне: <b>{int(counts.get('mine', 0))}</b>",
        f"Закрытые: <b>{int(counts.get('closed', 0))}</b>",
        "",
        _sep(),
        "📨 <b>ПОСЛЕДНИЕ ОБРАЩЕНИЯ</b>",
        _sep(),
    ]
    if tickets:
        for ticket in tickets[:visible_limit]:
            label = ticket.get("username") or ticket.get("full_name") or ticket.get("user_id")
            lines.append(
                f"• <b>{escape(str(label))}</b> — {escape(str(ticket.get('status') or 'new'))} · {escape(str(ticket.get('last_user_message_preview') or '—'))}"
            )
        hidden = max(int(counts.get(filter_mode, counts.get("all", len(tickets))) or 0) - min(len(tickets), visible_limit), 0)
        if hidden > 0:
            lines.extend(["", f"Ещё в очереди: <b>{hidden}</b>"])
    else:
        lines.append("Обращений по этому фильтру нет.")

    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="📂 Все", callback_data="control:support"),
            InlineKeyboardButton(text="🆕 Новые", callback_data="control:support:new"),
        ],
        [
            InlineKeyboardButton(text="🟡 В работе", callback_data="control:support:in_progress"),
            InlineKeyboardButton(text="🙋 На мне", callback_data="control:support:mine"),
        ],
    ]
    for ticket in tickets[:visible_limit]:
        label = str(ticket.get("username") or ticket.get("full_name") or ticket.get("user_id"))[:26]
        rows.append([InlineKeyboardButton(text=f"💬 {label}", callback_data=f"control:support:open:{int(ticket['user_id'])}")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def build_support_focus(ticket_user_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    payload = await get_v2_support_payload(ticket_id=ticket_user_id)
    selected = payload.get("selected_ticket")
    if selected is None:
        return "Обращение не найдено.", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬 Поддержка", callback_data="control:support")]])
    ticket = selected["ticket"]
    linked = selected.get("linked_user_context")
    lines = [
        "💬 <b>ОБРАЩЕНИЕ</b>",
        "",
        f"Клиент: <b>{escape(str(ticket.get('full_name') or ticket.get('username') or ticket.get('user_id')))}</b>",
        f"User ID: <code>{ticket.get('user_id')}</code>",
        f"Username: <b>{escape(str(ticket.get('username') or '—'))}</b>",
        f"Статус: <b>{escape(str(ticket.get('status') or 'new'))}</b>",
        f"Ответственный: <b>{escape(str(ticket.get('assigned_admin_name') or '—'))}</b>",
        f"Обновлено: <b>{escape(str(ticket.get('updated_at') or '—'))}</b>",
        "",
        _sep(),
        "🗨️ <b>ПОСЛЕДНИЕ СООБЩЕНИЯ</b>",
        _sep(),
    ]
    history = selected.get("history") or []
    if history:
        for item in history[-4:]:
            role_label = "Клиент" if item.get("role") == "user" else "Админ"
            lines.append(f"• <b>{role_label}:</b> {escape(str(item.get('text') or '—'))}")
    else:
        lines.append("История пока пуста.")
    if linked is not None:
        lines.extend(
            [
                "",
                _sep(),
                "👤 <b>USER CONTEXT</b>",
                _sep(),
                f"Тариф: <b>{escape(str(linked.get('plan_label') or '—'))}</b>",
                f"Доступ: <b>{escape(str(linked.get('status_label') or linked.get('access_status') or '—'))}</b>",
                f"Устройств: <b>{int(linked.get('devices_count') or 0)}/{int(linked.get('max_devices') or 3)}</b>",
                f"VPN repair: <b>{'да' if linked.get('vpn_repair_needed') else 'нет'}</b>",
            ]
        )
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="🙋 Взять", callback_data=f"control:support:assign:{ticket_user_id}"),
            InlineKeyboardButton(text="✉ Ответить", callback_data=f"control:support:reply:{ticket_user_id}"),
        ],
        [
            InlineKeyboardButton(text="🔁 Передать", callback_data=f"control:support:transfer:{ticket_user_id}"),
            InlineKeyboardButton(text="🔒 Закрыть", callback_data=f"control:support:close:{ticket_user_id}"),
        ],
    ]
    if linked is not None:
        rows.append(
            [
                InlineKeyboardButton(text="👤 Пользователь", callback_data=f"control:user:open:{int(linked['user_id'])}"),
                InlineKeyboardButton(text="🔄 Sync", callback_data=f"control:user:sync:{int(linked['user_id'])}"),
            ]
        )
        latest_payment_href = linked.get("latest_payment_href")
        if latest_payment_href and "record_id=" in latest_payment_href:
            try:
                payment_id = int(str(latest_payment_href).split("record_id=", 1)[1].split("&", 1)[0])
            except (TypeError, ValueError):
                payment_id = None
            if payment_id is not None:
                rows.append([InlineKeyboardButton(text="💳 Последний платёж", callback_data=f"control:payment:open:{payment_id}")])
    rows.append([InlineKeyboardButton(text="💬 Назад к поддержке", callback_data="control:support")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def build_settings_screen(viewer_telegram_id: int, target_telegram_id: int | None = None) -> tuple[str, InlineKeyboardMarkup | None]:
    role = control_role_for_telegram_id(viewer_telegram_id)
    profiles = await list_notification_preference_rows()
    if target_telegram_id is None or role != CONTROL_ROLE_OWNER:
        target_telegram_id = viewer_telegram_id
    target = next((row for row in profiles if row["telegram_id"] == int(target_telegram_id)), None)
    if target is None:
        return "⚙️ Настройки уведомлений не найдены.", None
    lines = [f"⚙️ <b>УВЕДОМЛЕНИЯ</b> — <code>{control_role_label(role)}</code>", ""]
    if role == CONTROL_ROLE_OWNER:
        lines.extend([_sep(), "👑 <b>УПРАВЛЕНИЕ АДМИНИСТРАТОРАМИ</b>", _sep(), "Выберите администратора для настройки уведомлений:", ""])
        for row in profiles:
            username = f"@{row['username']}" if row.get("username") else ""
            lines.append(
                f"👤 <b>{row['display_name']}</b> ({control_role_label(row['role'])}) — уведомления: {row['enabled_count']}/{row['total_count']} {username}".rstrip()
            )
        lines.append("")
    lines.extend(
        [
            _sep(),
            "🔔 <b>МОИ УВЕДОМЛЕНИЯ</b>" if target_telegram_id == viewer_telegram_id else "🔔 <b>НАСТРОЙКИ АДМИНИСТРАТОРА</b>",
            _sep(),
            f"👤 <b>{target['display_name']}</b> ({control_role_label(target['role'])}) — уведомления: {target['enabled_count']}/{target['total_count']}",
        ]
    )
    for category in NOTIFICATION_CATEGORIES:
        state = "✅" if target["preferences"].get(category, True) else "❌"
        mandatory = is_notification_category_mandatory(target["role"], category)
        suffix = " 🔒" if mandatory else ""
        lines.append(f"{state} {CATEGORY_LABELS.get(category, category)}{suffix}")
    lines.extend(
        [
            "",
            _sep(),
            "📊 <b>ОБЩАЯ СТАТИСТИКА</b>",
            _sep(),
            f"👥 Администраторов: {len(profiles)}",
            f"🔔 Включено уведомлений: {sum(row['enabled_count'] for row in profiles)}/{len(profiles) * len(NOTIFICATION_CATEGORIES)}",
            f"📨 Последняя отправка: {_fmt_short_dt(utcnow())}",
        ]
    )
    rows: list[list[InlineKeyboardButton]] = []
    if role == CONTROL_ROLE_OWNER:
        owner_row: list[InlineKeyboardButton] = []
        for row in profiles[:4]:
            owner_row.append(
                InlineKeyboardButton(
                    text=f"👤 {row['display_name'][:12]}",
                    callback_data=f"control:settings:admin:{row['telegram_id']}",
                )
            )
        if owner_row:
            rows.append(owner_row)
    toggle_rows: list[list[InlineKeyboardButton]] = []
    for category in NOTIFICATION_CATEGORIES:
        enabled = target["preferences"].get(category, True)
        mandatory = is_notification_category_mandatory(target["role"], category)
        toggle_rows.append(
            [
                InlineKeyboardButton(
                    text=f"{'🔒' if mandatory else ('✅' if enabled else '❌')} {CATEGORY_LABELS.get(category, category)}",
                    callback_data=(
                        f"control:settings:locked:{target_telegram_id}:{category}"
                        if mandatory
                        else f"control:settings:toggle:{target_telegram_id}:{category}"
                    ),
                )
            ]
        )
    rows.extend(toggle_rows)
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def build_broadcast_root_screen() -> tuple[str, InlineKeyboardMarkup | None]:
    counts = await segment_counts()
    recent = await list_recent_broadcast_campaigns(limit=10)
    sent_last_day = sum((row.sent_count or 0) for row in recent)
    lines = [
        "📢 <b>РАССЫЛКА И ТРИГГЕРЫ</b>",
        "",
        _sep(),
        "📨 <b>PUSH-УВЕДОМЛЕНИЯ АДМИНАМ</b>",
        _sep(),
        "Быстрая отправка сообщений всем администраторам",
        "",
        _sep(),
        "⚡ <b>АВТОМАТИЧЕСКИЕ ТРИГГЕРЫ</b>",
        _sep(),
        f"🎯 Активных триггеров: {len([row for row in await list_trigger_rules() if row.enabled])}/{len(await list_trigger_rules())}",
        f"📨 Отправлено за 24ч: {sum((row.sent_count or 0) for row in recent if row.scope == CAMPAIGN_SCOPE_TRIGGER)}",
        "",
        _sep(),
        "📢 <b>РУЧНАЯ РАССЫЛКА</b>",
        _sep(),
        f"👥 Всего пользователей: {counts['all']}",
        f"🎁 На пробном периоде: {counts['trial_active']}",
        f"💎 С активной подпиской: {counts['paid_active']}",
        f"⚪ С истекшей подпиской: {counts['expired']}",
        f"💤 Неактивные (30+ дней): {counts['inactive_30d']}",
        "",
        _sep(),
        "📊 <b>СТАТИСТИКА РАССЫЛОК</b>",
        _sep(),
        f"📨 Всего отправлено: {sent_last_day}",
        f"✅ Доставлено: {sum((row.sent_count or 0) for row in recent)}",
        f"👆 CTA-кликов: {sum((row.clicked_count or 0) for row in recent)}",
        f"📅 Последняя рассылка: { _fmt_dt(recent[0].created_at) if recent else '—' }",
    ]
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Админам", callback_data="control:broadcast:admin"),
                InlineKeyboardButton(text="⚡ Триггеры", callback_data="control:broadcast:triggers"),
            ],
            [
                InlineKeyboardButton(text="📢 Рассылка", callback_data="control:broadcast:users"),
                InlineKeyboardButton(text="📋 Шаблоны", callback_data="control:broadcast:templates"),
            ],
            [
                InlineKeyboardButton(text="📊 Статистика", callback_data="control:broadcast:stats"),
            ],
        ]
    )
    return "\n".join(lines), keyboard


async def build_admin_push_screen() -> tuple[str, InlineKeyboardMarkup | None]:
    profiles = await list_control_admin_profiles()
    lines = [
        "📨 <b>PUSH-УВЕДОМЛЕНИЕ АДМИНАМ</b>",
        "",
        _sep(),
        f"👥 <b>Получатели:</b> все администраторы ({len(profiles)})",
        _sep(),
        "",
        "📝 Нажмите «Написать», затем отправьте текст сообщения следующим сообщением.",
        "",
        _sep(),
        "🔔 <b>ДОПОЛНИТЕЛЬНО</b>",
        _sep(),
        "Приоритет: высокий / средний / низкий",
        "Отправка: сейчас или по времени",
    ]
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Написать", callback_data="control:broadcast:admin:compose"),
                InlineKeyboardButton(text="📋 Шаблоны", callback_data="control:broadcast:templates:admin_push"),
            ],
            [
                InlineKeyboardButton(text="Тест себе", callback_data="control:broadcast:admin:test"),
            ],
        ]
    )
    return "\n".join(lines), keyboard


async def build_user_broadcast_screen() -> tuple[str, InlineKeyboardMarkup | None]:
    counts = await segment_counts()
    lines = [
        "📢 <b>СОЗДАНИЕ РАССЫЛКИ</b> — <code>шаг 1/3</code>",
        "",
        _sep(),
        "🎯 <b>ВЫБОР ПОЛУЧАТЕЛЕЙ</b>",
        _sep(),
        f"👥 Все пользователи: {counts['all']}",
        f"🎁 Пробный период: {counts['trial_active']}",
        f"💎 Активная подписка: {counts['paid_active']}",
        f"⚪ Истекшая подписка: {counts['expired']}",
        f"💤 Неактивные (30+ дней): {counts['inactive_30d']}",
        f"🆕 Новые (за 7 дней): {counts['new_7d']}",
        "",
        f"📅 Заканчивается сегодня: {counts['expiring_today']}",
        f"📅 Заканчивается завтра: {counts['expiring_tomorrow']}",
        f"📅 Заканчивается через 3 дня: {counts['expiring_3d']}",
        f"📅 Заканчивается через 7 дней: {counts['expiring_7d']}",
        "",
        _sep(),
        "Нажмите сегмент ниже, затем следующим сообщением отправьте текст рассылки.",
    ]
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👥 Все", callback_data="control:broadcast:segment:all"),
                InlineKeyboardButton(text="🎁 Пробный", callback_data="control:broadcast:segment:trial_active"),
            ],
            [
                InlineKeyboardButton(text="💎 Активные", callback_data="control:broadcast:segment:paid_active"),
                InlineKeyboardButton(text="⚪ Истекшие", callback_data="control:broadcast:segment:expired"),
            ],
            [
                InlineKeyboardButton(text="📅 По дате", callback_data="control:broadcast:segment:expiring_3d"),
                InlineKeyboardButton(text="🟢 По активности", callback_data="control:broadcast:segment:inactive_7d"),
            ],
            [
                InlineKeyboardButton(text="📋 Шаблоны", callback_data="control:broadcast:templates:user_broadcast"),
            ],
        ]
    )
    return "\n".join(lines), keyboard


async def build_trigger_center_screen() -> tuple[str, InlineKeyboardMarkup | None]:
    grouped = await list_trigger_rules_grouped()
    rows = [row for rows in grouped.values() for row in rows]
    lines = [
        "⚡ <b>АВТОМАТИЧЕСКИЕ ТРИГГЕРЫ</b>",
        "",
        _sep(),
        "📊 <b>СТАТУС ТРИГГЕРОВ</b>",
        _sep(),
        f"🟢 Активных триггеров: {len([row for row in rows if row.enabled])}",
        f"🟡 В работе: {len([row for row in rows if row.enabled is False])}",
        "",
        _sep(),
        "🎯 <b>ДОСТУПНЫЕ ТРИГГЕРЫ</b>",
        _sep(),
    ]
    for family, family_rows in grouped.items():
        lines.append(f"<b>{family}</b>")
        for row in family_rows:
            icon = "✅" if row.enabled else "❌"
            lines.append(f"   {icon} {row.title}")
    keyboard_rows: list[list[InlineKeyboardButton]] = []
    for row in rows[:8]:
        keyboard_rows.append([InlineKeyboardButton(text=row.title[:42], callback_data=f"control:trigger:open:{row.id}")])
    keyboard_rows.append([InlineKeyboardButton(text="📋 Шаблоны", callback_data="control:broadcast:templates:trigger")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


async def build_trigger_rule_screen(rule_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    row = await get_trigger_rule(rule_id)
    if row is None:
        return "⚡ Триггер не найден.", None
    config = event_payload(type("Fake", (), {"payload_json": row.config_json})())
    buttons = serialize_template_buttons(row)
    lines = [
        f"⚙️ <b>НАСТРОЙКА ТРИГГЕРА</b> — <code>{row.title}</code>",
        "",
        _sep(),
        "📊 <b>ОБЩАЯ ИНФОРМАЦИЯ</b>",
        _sep(),
        f"🎯 Тип: {row.family}",
        f"Статус: {'✅ активен' if row.enabled else '❌ неактивен'}",
        f"Конфиг: <code>{escape(str(config))}</code>",
        "",
        _sep(),
        "📝 <b>ТЕКСТ СООБЩЕНИЯ</b>",
        _sep(),
        row.template_body,
        "",
        _sep(),
        "🔘 <b>CTA-КНОПКИ</b>",
        _sep(),
    ]
    if buttons:
        for button in buttons:
            lines.append(f"• {button.get('label') or CTA_ACTIONS.get(button.get('action', ''), button.get('action', '—'))}")
    else:
        lines.append("Без CTA-кнопок.")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Редактировать текст", callback_data=f"control:trigger:edit:{row.id}"),
                InlineKeyboardButton(text="✅ Вкл/Выкл", callback_data=f"control:trigger:toggle:{row.id}"),
            ],
            [
                InlineKeyboardButton(text="Тест себе", callback_data=f"control:trigger:test:{row.id}"),
            ],
        ]
    )
    return "\n".join(lines), keyboard


async def build_templates_screen(scope: str | None = None) -> tuple[str, InlineKeyboardMarkup | None]:
    templates = await list_message_templates(scope)
    label = {
        None: "все",
        "admin_push": "админам",
        "user_broadcast": "пользователям",
        "trigger": "триггерам",
    }.get(scope, scope or "все")
    lines = [f"📋 <b>ШАБЛОНЫ СООБЩЕНИЙ</b> — <code>{label}</code>", "", _sep(), "📁 <b>ГОТОВЫЕ ШАБЛОНЫ</b>", _sep()]
    if templates:
        for row in templates[:10]:
            marker = "📌" if not row.is_builtin else "📁"
            lines.append(f"{marker} <b>{row.name}</b>")
            lines.append(f"   └─ {row.body[:90]}")
    else:
        lines.append("Шаблонов пока нет.")
    keyboard_rows: list[list[InlineKeyboardButton]] = []
    for row in templates[:6]:
        keyboard_rows.append(
            [
                InlineKeyboardButton(text=f"📝 {row.name[:30]}", callback_data=f"control:template:open:{row.id}"),
            ]
        )
    keyboard_rows.append(
        [
            InlineKeyboardButton(text="➕ Новый шаблон", callback_data=f"control:template:new:{scope or 'all'}"),
        ]
    )
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


async def build_broadcast_stats_screen() -> tuple[str, InlineKeyboardMarkup | None]:
    rows = await list_recent_broadcast_campaigns(limit=10)
    lines = [
        "📊 <b>СТАТИСТИКА РАССЫЛОК</b>",
        "",
        _sep(),
        f"📨 Всего кампаний: {len(rows)}",
        f"✅ Доставлено: {sum((row.sent_count or 0) for row in rows)}",
        f"❌ Ошибки: {sum((row.failed_count or 0) for row in rows)}",
        f"👆 CTA-клики: {sum((row.clicked_count or 0) for row in rows)}",
        f"🎯 Конверсии: {sum((row.converted_count or 0) for row in rows)}",
        "",
        _sep(),
        "📋 <b>ПОСЛЕДНИЕ КАМПАНИИ</b>",
        _sep(),
    ]
    if rows:
        for row in rows[:8]:
            lines.append(
                f"• #{row.id} — {row.scope} / {row.status} / sent {row.sent_count} / failed {row.failed_count} / clicks {row.clicked_count}"
            )
    else:
        lines.append("Кампаний пока нет.")
    keyboard_rows: list[list[InlineKeyboardButton]] = []
    for row in rows[:3]:
        keyboard_rows.append(
            [InlineKeyboardButton(text=f"📢 Кампания #{row.id}", callback_data=f"control:campaign:open:{row.id}")]
        )
    keyboard_rows.append(
        [
            InlineKeyboardButton(text="🔄 Обновить", callback_data="control:broadcast:stats"),
        ]
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    return "\n".join(lines), keyboard


async def build_template_focus_screen(template_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    row = next((item for item in await list_message_templates() if item.id == int(template_id)), None)
    if row is None:
        return "Шаблон не найден.", None
    buttons = serialize_template_buttons(row)
    lines = [
        f"📋 <b>ШАБЛОН</b> — <code>{row.name}</code>",
        "",
        _sep(),
        f"Scope: <b>{row.scope}</b>",
        f"Builtin: <b>{'да' if row.is_builtin else 'нет'}</b>",
        "",
        _sep(),
        row.body,
        "",
        _sep(),
        "CTA:",
    ]
    if buttons:
        for button in buttons:
            lines.append(f"• {button.get('label') or button.get('action')}")
    else:
        lines.append("Без кнопок")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Использовать", callback_data=f"control:template:use:{row.id}"),
                InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"control:template:edit:{row.id}"),
            ],
            [
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"control:template:delete:{row.id}"),
            ],
        ]
    )
    return "\n".join(lines), keyboard


async def build_campaign_focus_screen(campaign_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    campaign = await get_broadcast_campaign(campaign_id)
    if campaign is None:
        return "Рассылка не найдена.", None
    metadata = serialize_campaign_metadata(campaign)
    buttons = serialize_template_buttons(campaign)
    lines = [
        f"📢 <b>КАМПАНИЯ</b> — <code>#{campaign.id}</code>",
        "",
        _sep(),
        f"Scope: <b>{campaign.scope}</b>",
        f"Статус: <b>{campaign.status}</b>",
        f"Аудитория: <b>{campaign.audience_key or '—'}</b>",
        f"Приоритет: <b>{campaign.priority_label or '—'}</b>",
        f"Scheduled at: <b>{_fmt_dt(campaign.scheduled_at)}</b>",
        "",
        _sep(),
        campaign.message_body,
        "",
        _sep(),
        f"Target: {campaign.target_count} | Sent: {campaign.sent_count} | Failed: {campaign.failed_count} | Clicks: {campaign.clicked_count} | Conversions: {campaign.converted_count}",
        f"Meta: <code>{escape(str(metadata))}</code>",
    ]
    if buttons:
        lines.extend(["", _sep(), "CTA:"])
        for button in buttons:
            lines.append(f"• {button.get('label') or button.get('action')}")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data=f"control:campaign:open:{campaign.id}"),
            ]
        ]
    )
    return "\n".join(lines), keyboard


async def _load_status_dependencies():
    services = await get_service_statuses(force_refresh=True)
    snapshots = await get_server_snapshots(force_refresh=True)
    support_counts = await get_support_dashboard_counts()
    unresolved_critical = await list_control_events(severities={"CRITICAL"}, unresolved_only=True, limit=20)
    payment_rows = await list_payment_records(statuses={"awaiting_admin_review", "awaiting_user_payment", "confirmed"})
    traffic_payload = await get_v2_traffic_payload(force_refresh=True)
    return services, snapshots, support_counts, unresolved_critical, payment_rows, traffic_payload
