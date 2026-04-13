from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy import select

from backend.core.database import async_session
from backend.core.models import User, VpnClient
from backend.core.synthetic_users import real_user_sql_clause as shared_real_user_sql_clause
from bot.config import config
from bot.utils.access import has_active_access_from_user
from bot.utils.regions import (
    get_country_runtime_type,
    get_country_name,
    get_region_limit_rule,
    normalize_country_code,
    parse_load_average,
    region_soft_limit_reasons,
)
from dashboard.services import create_audit_log, ensure_current_traffic_baseline, get_server_snapshots
from control_bot.dispatcher import create_control_event


STATE_PATH = Path(__file__).resolve().parent / "state" / "server_watchdog_state.json"
VPN_REGION_CODES = {"de", "ee", "dk", "se"}
WATCHDOG_TIMEZONE = ZoneInfo("Asia/Yekaterinburg")
WATCHDOG_TIMEZONE_LABEL = "Екб"
WATCHDOG_CONFIRMATION_THRESHOLDS = {
    "down": 2,
    "overloaded": 2,
    "degraded": 3,
}
def _utcnow_label() -> str:
    return datetime.now(WATCHDOG_TIMEZONE).strftime(f"%Y-%m-%d %H:%M {WATCHDOG_TIMEZONE_LABEL}")


def _node_name(snapshot: dict) -> str:
    country_code = normalize_country_code(snapshot.get("country_code"))
    if country_code == "se":
        return "Швеция"
    return snapshot.get("country_name") or get_country_name(country_code)


def _fmt_duration_minutes(minutes: int) -> str:
    minutes = max(int(minutes), 0)
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours} часов, {mins} минут"


def _minutes_since_label(label: str | None) -> int | None:
    if not label:
        return None
    try:
        parsed = datetime.strptime(label.replace(f" {WATCHDOG_TIMEZONE_LABEL}", ""), "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    localized = parsed.replace(tzinfo=WATCHDOG_TIMEZONE)
    return int((datetime.now(WATCHDOG_TIMEZONE) - localized).total_seconds() // 60)


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {"incidents": {}, "pending": {}}
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"incidents": {}, "pending": {}}
    payload.setdefault("incidents", {})
    payload.setdefault("pending", {})
    return payload


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_relevant_server(snapshot: dict) -> bool:
    return normalize_country_code(snapshot.get("country_code")) in VPN_REGION_CODES


def _node_notifications_allowed(snapshot: dict, incident_kind: str, *, recovered: bool = False) -> bool:
    country_code = normalize_country_code(snapshot.get("country_code"))
    if country_code != "ee":
        return True
    if recovered:
        return incident_kind == "down"
    return incident_kind == "down"


def _vpn_runtime_label(snapshot: dict) -> str:
    runtime_type = get_country_runtime_type(snapshot.get("country_code"))
    if runtime_type == "retired":
        return "Retired"
    if runtime_type == "xray_core":
        return "Xray"
    if runtime_type == "amneziawg":
        return "AmneziaWG"
    return "3x-ui"


def _vpn_runtime_status(snapshot: dict) -> str | None:
    runtime_type = get_country_runtime_type(snapshot.get("country_code"))
    if runtime_type == "retired":
        return "n/a"
    if runtime_type == "amneziawg":
        return snapshot.get("awg_service_status")
    if runtime_type == "xray_core":
        return snapshot.get("xray_service_status")
    runtime_status = snapshot.get("xui_service_status")
    if str(runtime_status or "").strip().lower() in {"", "unknown"}:
        runtime_status = snapshot.get("xui_status")
    return runtime_status


def _vpn_runtime_service_status(snapshot: dict) -> str | None:
    runtime_type = get_country_runtime_type(snapshot.get("country_code"))
    if runtime_type == "retired":
        return "n/a"
    if runtime_type == "amneziawg":
        return snapshot.get("awg_service_status")
    if runtime_type == "xray_core":
        return snapshot.get("xray_service_status")
    return snapshot.get("xui_service_status")


def _vpn_control_plane_status(snapshot: dict) -> str | None:
    runtime_type = get_country_runtime_type(snapshot.get("country_code"))
    if runtime_type != "xui":
        return _vpn_runtime_status(snapshot)
    control_status = snapshot.get("xui_status")
    if str(control_status or "").strip().lower() in {"", "unknown"}:
        control_status = snapshot.get("xui_service_status")
    return control_status


def _has_monitoring_gap(snapshot: dict) -> bool:
    if snapshot.get("status") == "disabled":
        return False
    runtime_status = str(_vpn_control_plane_status(snapshot) or "").strip().lower()
    if runtime_status not in {"active", "ok"}:
        return False
    host_status = str(snapshot.get("host_status") or "").strip().lower()
    ssh_status = str(snapshot.get("ssh_status") or "").strip().lower()
    return host_status not in {"", "ok"} or ssh_status not in {"", "active", "ok"}


def _server_down_reason(snapshot: dict) -> str:
    reasons: list[str] = []
    if snapshot.get("host_status") not in {None, "ok"}:
        reasons.append("узел недоступен по health-check")
    if snapshot.get("ssh_status") not in {None, "active", "ok"}:
        reasons.append(f"ssh={snapshot.get('ssh_status')}")
    runtime_status = _vpn_runtime_status(snapshot)
    if runtime_status in {"error", "failed"}:
        reasons.append(f"{_vpn_runtime_label(snapshot)} недоступен")
    if snapshot.get("ping_label") and snapshot.get("ping_label") != "—":
        reasons.append(f"ping {snapshot['ping_label']}")
    return "; ".join(dict.fromkeys(reasons)) or "сервер перестал отдавать нормальный health"


def _is_server_down(snapshot: dict) -> bool:
    if snapshot.get("status") == "disabled":
        return False
    if _has_monitoring_gap(snapshot):
        return False
    if snapshot.get("host_status") not in {None, "ok"}:
        return True
    if snapshot.get("ssh_status") not in {None, "active", "ok"}:
        return True
    if _vpn_runtime_status(snapshot) in {"error", "failed"}:
        return True
    return False


def _is_server_overloaded(snapshot: dict) -> bool:
    if snapshot.get("status") == "disabled" or _is_server_down(snapshot):
        return False

    rule = get_region_limit_rule(snapshot.get("country_code"))
    reasons = region_soft_limit_reasons(
        rule,
        active_devices=int(snapshot.get("active_devices") or 0),
        cpu_used_percent=float(snapshot.get("cpu_percent") or 0),
        memory_used_percent=float(snapshot.get("memory_used_percent") or 0),
        disk_used_percent=float(snapshot.get("disk_used_percent") or 0),
        load_average=parse_load_average(snapshot.get("load")),
    )
    return bool(reasons)


def _server_overload_reason(snapshot: dict) -> str:
    rule = get_region_limit_rule(snapshot.get("country_code"))
    reasons = region_soft_limit_reasons(
        rule,
        active_devices=int(snapshot.get("active_devices") or 0),
        cpu_used_percent=float(snapshot.get("cpu_percent") or 0),
        memory_used_percent=float(snapshot.get("memory_used_percent") or 0),
        disk_used_percent=float(snapshot.get("disk_used_percent") or 0),
        load_average=parse_load_average(snapshot.get("load")),
    )
    return "; ".join(dict.fromkeys(reasons)) or "ресурсный порог превышен"


def _is_server_degraded(snapshot: dict) -> bool:
    if snapshot.get("status") == "disabled" or _is_server_down(snapshot) or _is_server_overloaded(snapshot):
        return False
    if _has_monitoring_gap(snapshot):
        return False
    if snapshot.get("overall_state") == "warning":
        return True
    if _vpn_runtime_service_status(snapshot) not in {None, "active", "ok", "n/a"}:
        return True
    return False


def _server_degraded_reason(snapshot: dict) -> str:
    reasons: list[str] = []
    if snapshot.get("cpu_state") == "warning":
        reasons.append(f"CPU {float(snapshot.get('cpu_percent') or 0):.1f}%")
    if snapshot.get("memory_state") == "warning":
        reasons.append(f"RAM {float(snapshot.get('memory_used_percent') or 0):.1f}%")
    if snapshot.get("disk_state") == "warning":
        reasons.append(f"disk {float(snapshot.get('disk_used_percent') or 0):.1f}%")
    if snapshot.get("ping_state") == "warning" and snapshot.get("ping_label") and snapshot.get("ping_label") != "—":
        reasons.append(f"ping {snapshot['ping_label']}")
    runtime_service_status = _vpn_runtime_service_status(snapshot)
    if runtime_service_status not in {None, "active", "ok", "n/a"}:
        reasons.append(f"{_vpn_runtime_label(snapshot)} service={runtime_service_status}")
    return "; ".join(dict.fromkeys(reasons)) or "узел работает нестабильно, но ещё не перегружен"


def _pending_key(server_id: str) -> str:
    return str(server_id)


def _advance_pending(
    pending: dict[str, dict],
    server_id: str,
    kind: str,
    reason: str,
) -> tuple[bool, int]:
    key = _pending_key(server_id)
    current = pending.get(key)
    if current and current.get("kind") == kind:
        count = int(current.get("count") or 0) + 1
    else:
        count = 1
    pending[key] = {
        "kind": kind,
        "count": count,
        "reason": reason,
        "last_seen_at": _utcnow_label(),
    }
    threshold = WATCHDOG_CONFIRMATION_THRESHOLDS.get(kind, 2)
    return count >= threshold, count


async def _affected_user_ids(country_code: str) -> list[int]:
    normalized_code = normalize_country_code(country_code)
    async with async_session() as session:
        rows = list(
            (
                await session.execute(
                    select(VpnClient.user_id, VpnClient.client_data, User)
                    .join(User, User.id == VpnClient.user_id)
                    .where(shared_real_user_sql_clause(User))
                )
            ).all()
        )

    affected: set[int] = set()
    for user_id, client_data, user in rows:
        if user_id in affected:
            continue
        try:
            metadata = json.loads(client_data or "{}")
        except json.JSONDecodeError:
            metadata = {}
        if normalize_country_code(metadata.get("country_code")) != normalized_code:
            continue
        if user is None or not has_active_access_from_user(user):
            continue
        affected.add(int(user_id))
    return sorted(affected)


async def _safe_send(bot: Bot, chat_id: int, text: str) -> bool:
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", disable_web_page_preview=True)
        return True
    except (TelegramForbiddenError, TelegramBadRequest):
        return False


async def _notify_admins(
    snapshot: dict,
    reason: str,
    recovered: bool = False,
    incident_kind: str = "down",
    previous_kind: str | None = None,
    duration_minutes: int | None = None,
) -> None:
    if not _node_notifications_allowed(snapshot, incident_kind, recovered=recovered):
        return
    node_name = _node_name(snapshot)
    if recovered:
        title = f"Нода {node_name} восстановлена"
        severity = "INFO"
        event_type = "node_recovered"
    elif incident_kind == "overloaded":
        title = f"Нода {node_name} перегружена"
        severity = "WARNING"
        event_type = "node_overloaded"
    elif incident_kind == "degraded":
        title = f"Нода {node_name} требует внимания"
        severity = "WARNING"
        event_type = "node_degraded"
    else:
        title = f"Нода {node_name} недоступна"
        severity = "CRITICAL"
        event_type = "node_offline"
    if recovered and duration_minutes is not None:
        message = f"была недоступна {_fmt_duration_minutes(duration_minutes)}"
        delivery_text = f"🟢 <b>{title}</b> ({message})"
    else:
        message = reason
        delivery_text = f"{'🔴' if severity == 'CRITICAL' else '🟡' if severity == 'WARNING' else '🟢'} <b>{title}</b>\n{reason}"
    await create_control_event(
        category="nodes",
        severity=severity,
        event_type=event_type,
        title=title,
        message=message,
        entity_type="managed_server",
        entity_id=str(snapshot.get("id") or ""),
        payload={
            "server_id": snapshot.get("id"),
            "country_code": snapshot.get("country_code"),
            "country_name": snapshot.get("country_name"),
            "incident_kind": incident_kind,
            "previous_kind": previous_kind,
            "reason": reason,
            "duration_minutes": duration_minutes,
        },
        dedupe_key=f"node:{snapshot.get('id')}:{incident_kind}",
        resolve_dedupe_key=f"node:{snapshot.get('id')}:{previous_kind}" if previous_kind else None,
        delivery_text=delivery_text,
    )


async def _notify_affected_users(bot: Bot, snapshot: dict, user_ids: list[int], recovered: bool = False) -> None:
    if not _node_notifications_allowed(snapshot, "down", recovered=recovered):
        return
    region = snapshot.get("country_name") or get_country_name(snapshot.get("country_code"))
    if recovered:
        text = (
            "✅ <b>Технические работы завершены</b>\n\n"
            f"Сервер <b>{region}</b> снова доступен. Если подключение не восстановилось сразу, переподключи VPN."
        )
    else:
        text = (
            "⚙️ <b>Технические работы на сервере</b>\n\n"
            f"Сервер <b>{region}</b> сейчас проходит восстановление. "
            "Ориентир по времени — около 15 минут. Как только узел вернётся в строй, доступ восстановится автоматически."
        )
    for user_id in user_ids:
        await _safe_send(bot, user_id, text)


async def main() -> None:
    token = config.bot_token or config.support_bot_token
    if not token:
        raise RuntimeError("Bot token is not configured")

    state = _load_state()
    incidents: dict[str, dict] = state.setdefault("incidents", {})
    pending: dict[str, dict] = state.setdefault("pending", {})
    snapshots = [snapshot for snapshot in await get_server_snapshots(force_refresh=True) if _is_relevant_server(snapshot)]
    await ensure_current_traffic_baseline(snapshots)

    bot = Bot(token)
    try:
        active_server_ids = {str(snapshot.get("id")) for snapshot in snapshots}
        for snapshot in snapshots:
            server_id = str(snapshot.get("id"))
            is_down = _is_server_down(snapshot)
            is_overloaded = _is_server_overloaded(snapshot)
            is_degraded = _is_server_degraded(snapshot)
            current_kind = "down" if is_down else "overloaded" if is_overloaded else "degraded" if is_degraded else None
            incident = incidents.get(server_id)

            if current_kind is None:
                pending.pop(server_id, None)
            if current_kind is not None and incident is None:
                if current_kind == "down":
                    reason = _server_down_reason(snapshot)
                elif current_kind == "overloaded":
                    reason = _server_overload_reason(snapshot)
                else:
                    reason = _server_degraded_reason(snapshot)
                should_open, confirmations = _advance_pending(pending, server_id, current_kind, reason)
                if should_open:
                    affected_users = await _affected_user_ids(snapshot.get("country_code")) if current_kind == "down" else []
                    await _notify_admins(snapshot, reason, recovered=False, incident_kind=current_kind)
                    if current_kind == "down" and affected_users:
                        await _notify_affected_users(bot, snapshot, affected_users, recovered=False)
                    incidents[server_id] = {
                        "opened_at": _utcnow_label(),
                        "opened_at_ts": datetime.now(WATCHDOG_TIMEZONE).isoformat(),
                        "kind": current_kind,
                        "reason": reason,
                        "users": affected_users,
                    }
                    pending.pop(server_id, None)
                    await create_audit_log(
                        None,
                        {
                            "down": "server_watchdog_down",
                            "overloaded": "server_watchdog_overloaded",
                            "degraded": "server_watchdog_degraded",
                        }[current_kind],
                        "managed_server",
                        server_id,
                        json.dumps(
                            {
                                "name": snapshot.get("name"),
                                "country": snapshot.get("country_name"),
                                "reason": reason,
                                "kind": current_kind,
                                "confirmations": confirmations,
                            },
                            ensure_ascii=False,
                        ),
                        None,
                    )
            elif current_kind is None and incident is not None:
                recovery_reason = "health-check снова зелёный"
                duration_minutes = _minutes_since_label(incident.get("opened_at"))
                await _notify_admins(
                    snapshot,
                    recovery_reason,
                    recovered=True,
                    incident_kind=incident.get("kind") or "down",
                    previous_kind=incident.get("kind"),
                    duration_minutes=duration_minutes,
                )
                if incident.get("kind") == "down" and incident.get("users"):
                    await _notify_affected_users(bot, snapshot, incident.get("users", []), recovered=True)
                incidents.pop(server_id, None)
                await create_audit_log(
                    None,
                    "server_watchdog_recovered",
                    "managed_server",
                    server_id,
                    json.dumps(
                        {
                            "name": snapshot.get("name"),
                            "country": snapshot.get("country_name"),
                            "previous_kind": incident.get("kind"),
                        },
                        ensure_ascii=False,
                    ),
                    None,
                )
            elif current_kind is not None and incident is not None and incident.get("kind") != current_kind:
                if current_kind == "down":
                    reason = _server_down_reason(snapshot)
                elif current_kind == "overloaded":
                    reason = _server_overload_reason(snapshot)
                else:
                    reason = _server_degraded_reason(snapshot)
                affected_users = await _affected_user_ids(snapshot.get("country_code")) if current_kind == "down" else []
                await _notify_admins(
                    snapshot,
                    reason,
                    recovered=False,
                    incident_kind=current_kind,
                    previous_kind=incident.get("kind"),
                )
                if current_kind == "down" and affected_users:
                    await _notify_affected_users(bot, snapshot, affected_users, recovered=False)
                incidents[server_id] = {
                    "opened_at": _utcnow_label(),
                    "kind": current_kind,
                    "reason": reason,
                    "users": affected_users,
                }
                pending.pop(server_id, None)

        stale_server_ids = [server_id for server_id in incidents if server_id not in active_server_ids]
        for server_id in stale_server_ids:
            incidents.pop(server_id, None)
            pending.pop(server_id, None)

        _save_state(state)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
