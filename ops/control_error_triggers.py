from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from html import escape
from typing import Any, Iterable

from sqlalchemy import select

from backend.core.database import async_session
from backend.core.models import ControlNotificationEvent, User, VpnClient
from backend.core.synthetic_users import (
    is_synthetic_user as shared_is_synthetic_user,
    real_user_sql_clause as shared_real_user_sql_clause,
)
from bot.repair_reasons import is_payment_related_repair_reason, normalize_repair_reason, repair_reason_label
from bot.utils.access import get_access_status_from_user, utcnow
from control_bot.dispatcher import create_control_event
from dashboard.services import dashboard_server_state, get_server_snapshots

USER_REPAIR_ESCALATION_HOURS = 6
SERVICE_HEALTHY_STATES = {"active"}
SERVICE_WARNING_STATES = {"activating", "reloading", "deactivating", "unknown"}
SERVICE_CRITICAL_STATES = {"inactive", "failed", "dead", "not-found"}
MONITORED_SERVICE_UNITS = {
    "main_bot": ("amonora-bot.service", "Main bot"),
    "support_bot": ("amonora-support-bot.service", "Support bot"),
    "control_bot": ("amonora-control-bot.service", "Control bot"),
    "dashboard": ("amonora-dashboard.service", "Dashboard backend"),
    "dashboard_ui": ("amonora-dashboard-ui.service", "Dashboard UI"),
    "landing": ("amonora-landing.service", "Landing"),
    "nginx": ("nginx.service", "Nginx"),
    "access_reminders_timer": ("amonora-access-reminders.timer", "Access reminders timer"),
    "server_watchdog_timer": ("amonora-server-watchdog.timer", "Server watchdog timer"),
}
USER_ACCESS_DEDUPE_KEY = "control-health:users:repair-needed"
@dataclass(frozen=True)
class IncidentSpec:
    category: str
    severity: str
    event_type: str
    title: str
    message: str
    entity_type: str | None
    entity_id: str | None
    payload: dict[str, Any]
    dedupe_key: str


@dataclass(frozen=True)
class RecoverySpec:
    category: str
    event_type: str
    title: str
    message: str
    entity_type: str | None
    entity_id: str | None
    payload: dict[str, Any]
    incident_dedupe_key: str
    recovery_dedupe_key: str


def _is_synthetic_user(user: User) -> bool:
    return shared_is_synthetic_user(user)


async def _systemctl_is_active(unit_name: str) -> str:
    process = await asyncio.create_subprocess_exec(
        "systemctl",
        "is-active",
        unit_name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await process.communicate()
    output = stdout.decode("utf-8", errors="ignore").strip().lower()
    return output or "unknown"


async def load_monitored_service_statuses() -> dict[str, dict[str, str]]:
    async def _probe(service_key: str, unit_name: str, label: str) -> tuple[str, dict[str, str]]:
        status = await _systemctl_is_active(unit_name)
        return service_key, {"label": unit_name, "service_label": label, "status": status}

    rows = await asyncio.gather(
        *[
            _probe(service_key, unit_name, label)
            for service_key, (unit_name, label) in MONITORED_SERVICE_UNITS.items()
        ]
    )
    return dict(rows)


def _build_repair_needed_users_query():
    return select(User).where(
        shared_real_user_sql_clause(User),
        User.vpn_repair_needed.is_(True),
        User.telegram_id.is_not(None),
    )


async def _load_user_repair_inputs() -> tuple[list[User], dict[int, int]]:
    async with async_session() as session:
        users = list((await session.execute(_build_repair_needed_users_query())).scalars().all())
        user_ids = sorted({int(user.id) for user in users if getattr(user, "id", None) is not None})
        if user_ids:
            device_rows = list(
                (
                    await session.execute(
                        select(VpnClient.user_id).where(VpnClient.user_id.in_(user_ids))
                    )
                ).scalars().all()
            )
        else:
            device_rows = []

    device_counts: dict[int, int] = Counter(int(user_id) for user_id in device_rows if user_id is not None)
    return users, device_counts


async def _list_unresolved_incident_keys(keys: Iterable[str]) -> set[str]:
    normalized = sorted({str(key).strip() for key in keys if str(key).strip()})
    if not normalized:
        return set()
    async with async_session() as session:
        rows = list(
            (
                await session.execute(
                    select(ControlNotificationEvent.dedupe_key).where(
                        ControlNotificationEvent.dedupe_key.in_(normalized),
                        ControlNotificationEvent.resolved_at.is_(None),
                    )
                )
            ).scalars().all()
        )
    return {row for row in rows if row}


async def _mark_event_resolved(event_id: int) -> None:
    async with async_session() as session:
        row = (
            await session.execute(select(ControlNotificationEvent).where(ControlNotificationEvent.id == int(event_id)))
        ).scalar_one_or_none()
        if row is None or row.resolved_at is not None:
            return
        row.resolved_at = utcnow()
        await session.commit()


def _service_incident_key(service_key: str) -> str:
    return f"control-health:service:{service_key}"


def _node_incident_key(server_id: int) -> str:
    return f"control-health:node:{int(server_id)}"


def _node_incident_allowed(snapshot: dict[str, Any], state_code: str) -> bool:
    if bool(snapshot.get("is_local")):
        return state_code == "down"
    country_code = str(snapshot.get("country_code") or "").strip().lower()
    if country_code != "ee":
        return True
    return state_code == "down"


def _service_incident_and_recovery(
    service_key: str,
    payload: dict[str, str],
) -> tuple[IncidentSpec | None, RecoverySpec]:
    unit_name = str(payload.get("label") or MONITORED_SERVICE_UNITS.get(service_key, (service_key, service_key))[0])
    service_label = str(payload.get("service_label") or MONITORED_SERVICE_UNITS.get(service_key, (unit_name, service_key))[1])
    status = str(payload.get("status") or "unknown").strip().lower() or "unknown"
    dedupe_key = _service_incident_key(service_key)

    recovery = RecoverySpec(
        category="errors",
        event_type="service_recovered",
        title="Сервис восстановился",
        message=(
            f"Сервис: <b>{escape(service_label)}</b>\n"
            f"Unit: <code>{escape(unit_name)}</code>\n"
            "Состояние вернулось в <b>active</b>."
        ),
        entity_type="service",
        entity_id=unit_name,
        payload={"service_key": service_key, "unit_name": unit_name, "status": "active"},
        incident_dedupe_key=dedupe_key,
        recovery_dedupe_key=f"{dedupe_key}:recovered",
    )

    if status in SERVICE_HEALTHY_STATES:
        return None, recovery

    severity = "WARNING" if status in SERVICE_WARNING_STATES else "CRITICAL"
    title = "Сервис требует внимания" if severity == "WARNING" else "Сервис недоступен"
    incident = IncidentSpec(
        category="errors",
        severity=severity,
        event_type="service_health_issue",
        title=title,
        message=(
            f"Сервис: <b>{escape(service_label)}</b>\n"
            f"Unit: <code>{escape(unit_name)}</code>\n"
            f"Статус: <b>{escape(status)}</b>"
        ),
        entity_type="service",
        entity_id=unit_name,
        payload={
            "service_key": service_key,
            "service_label": service_label,
            "unit_name": unit_name,
            "status": status,
        },
        dedupe_key=dedupe_key,
    )
    return incident, recovery


def build_service_incident_specs(
    statuses: dict[str, dict[str, str]],
) -> tuple[list[IncidentSpec], dict[str, RecoverySpec]]:
    incidents: list[IncidentSpec] = []
    recoveries: dict[str, RecoverySpec] = {}
    for service_key, (unit_name, label) in MONITORED_SERVICE_UNITS.items():
        incident, recovery = _service_incident_and_recovery(
            service_key,
            statuses.get(service_key, {"label": unit_name, "service_label": label, "status": "unknown"}),
        )
        recoveries[recovery.incident_dedupe_key] = recovery
        if incident is not None:
            incidents.append(incident)
    return incidents, recoveries


def _node_incident_and_recovery(snapshot: dict[str, Any]) -> tuple[IncidentSpec | None, RecoverySpec]:
    server_id = int(snapshot.get("id") or 0)
    state = dashboard_server_state(snapshot)
    dedupe_key = _node_incident_key(server_id)
    name = str(snapshot.get("name") or f"server-{server_id}")
    region = str(snapshot.get("country_name") or snapshot.get("country_code") or "—")
    state_code = str(state.get("code") or "unknown")
    state_label = str(state.get("label") or state_code)

    recovery = RecoverySpec(
        category="nodes",
        event_type="node_recovered",
        title="Нода восстановилась",
        message=(
            f"Нода: <b>{escape(name)}</b>\n"
            f"Регион: <b>{escape(region)}</b>\n"
            "Состояние вернулось в рабочий режим."
        ),
        entity_type="server",
        entity_id=str(server_id),
        payload={"server_id": server_id, "name": name, "country_name": region, "state": "active"},
        incident_dedupe_key=dedupe_key,
        recovery_dedupe_key=f"{dedupe_key}:recovered",
    )

    if state_code in {"active", "maintenance"}:
        return None, recovery

    if not _node_incident_allowed(snapshot, state_code):
        return None, recovery

    runtime_state = str(snapshot.get("runtime_state") or "").strip().lower()
    overall_state = str(snapshot.get("overall_state") or "").strip().lower()
    if state_code == "degradation" and runtime_state != "critical" and overall_state != "critical":
        return None, recovery

    runtime_status = (
        snapshot.get("xray_service_status")
        or snapshot.get("awg_service_status")
        or snapshot.get("xui_service_status")
        or snapshot.get("xui_status")
    )
    severity = "CRITICAL" if state_code == "down" else "WARNING"
    title = "Нода недоступна" if severity == "CRITICAL" else "Нода деградирует"
    incident = IncidentSpec(
        category="nodes",
        severity=severity,
        event_type="node_health_issue",
        title=title,
        message=(
            f"Нода: <b>{escape(name)}</b>\n"
            f"Регион: <b>{escape(region)}</b>\n"
            f"Состояние: <b>{escape(state_label)}</b>\n"
            f"Общий health: <b>{escape(str(snapshot.get('overall_state') or 'unknown'))}</b>\n"
            f"Runtime: <code>{escape(str(runtime_status or '—'))}</code>\n"
            f"Ping: <b>{escape(str(snapshot.get('ping_label') or '—'))}</b>\n"
            f"{escape(str(snapshot.get('status_message') or ''))}"
        ),
        entity_type="server",
        entity_id=str(server_id),
        payload={
            "server_id": server_id,
            "name": name,
            "country_name": region,
            "state_code": state_code,
            "state_label": state_label,
            "overall_state": snapshot.get("overall_state"),
            "runtime_status": runtime_status,
            "ping_label": snapshot.get("ping_label"),
        },
        dedupe_key=dedupe_key,
    )
    return incident, recovery


def build_node_incident_specs(
    snapshots: list[dict[str, Any]],
) -> tuple[list[IncidentSpec], dict[str, RecoverySpec]]:
    incidents: list[IncidentSpec] = []
    recoveries: dict[str, RecoverySpec] = {}
    for snapshot in snapshots:
        incident, recovery = _node_incident_and_recovery(snapshot)
        recoveries[recovery.incident_dedupe_key] = recovery
        if incident is not None:
            incidents.append(incident)
    return incidents, recoveries


def _user_label(user: User) -> str:
    if getattr(user, "username", None):
        return f"@{user.username}"
    return f"TG {user.telegram_id}"


def build_user_incident_specs(
    users: list[User],
    device_counts: dict[int, int],
    *,
    now_utc: datetime | None = None,
) -> tuple[list[IncidentSpec], dict[str, RecoverySpec]]:
    now_utc = now_utc or utcnow()
    recovery = RecoverySpec(
        category="access",
        event_type="user_access_recovered",
        title="Пользовательские access-инциденты закрыты",
        message="Сейчас нет пользователей с активным состоянием <b>vpn_repair_needed</b>.",
        entity_type="users",
        entity_id="repair_needed",
        payload={"scope": "repair_needed", "status": "healthy"},
        incident_dedupe_key=USER_ACCESS_DEDUPE_KEY,
        recovery_dedupe_key=f"{USER_ACCESS_DEDUPE_KEY}:recovered",
    )

    rows: list[dict[str, Any]] = []
    for user in users:
        if _is_synthetic_user(user) or not bool(getattr(user, "vpn_repair_needed", False)):
            continue

        marked_at = getattr(user, "vpn_repair_marked_at", None) or now_utc
        marked_age_hours = max(int((now_utc - marked_at).total_seconds() // 3600), 0)
        reason = normalize_repair_reason(getattr(user, "vpn_repair_reason", None))
        rows.append(
            {
                "user_id": int(user.id),
                "telegram_id": int(user.telegram_id),
                "label": _user_label(user),
                "access_status": get_access_status_from_user(user),
                "devices_count": int(device_counts.get(int(user.id), 0)),
                "reason": reason,
                "reason_label": repair_reason_label(reason) or "Unknown",
                "marked_age_hours": marked_age_hours,
                "payment_related": is_payment_related_repair_reason(reason),
            }
        )

    if not rows:
        return [], {recovery.incident_dedupe_key: recovery}

    rows.sort(
        key=lambda item: (
            0 if item["payment_related"] else 1,
            -int(item["marked_age_hours"]),
            item["user_id"],
        )
    )
    payment_related = sum(1 for item in rows if item["payment_related"])
    stale = sum(1 for item in rows if int(item["marked_age_hours"]) >= USER_REPAIR_ESCALATION_HOURS)
    without_devices = sum(1 for item in rows if int(item["devices_count"]) <= 0)
    severity = "CRITICAL" if payment_related > 0 or stale > 0 else "WARNING"
    top_examples = rows[:3]
    examples_line = ", ".join(
        f"{escape(str(item['label']))} (#{item['user_id']}, {item['reason_label']})" for item in top_examples
    )
    incident = IncidentSpec(
        category="access",
        severity=severity,
        event_type="user_access_issue",
        title="Пользователи требуют срочной проверки" if severity == "CRITICAL" else "Есть проблемы с доступом пользователей",
        message=(
            f"Repair-needed пользователей: <b>{len(rows)}</b>\n"
            f"Платёжных инцидентов: <b>{payment_related}</b>\n"
            f"Застарелых (>={USER_REPAIR_ESCALATION_HOURS}ч): <b>{stale}</b>\n"
            f"Без устройств: <b>{without_devices}</b>\n"
            f"Примеры: <b>{examples_line or '—'}</b>"
        ),
        entity_type="users",
        entity_id="repair_needed",
        payload={
            "scope": "repair_needed",
            "total": len(rows),
            "payment_related": payment_related,
            "stale": stale,
            "without_devices": without_devices,
            "users": rows[:10],
        },
        dedupe_key=USER_ACCESS_DEDUPE_KEY,
    )
    return [incident], {recovery.incident_dedupe_key: recovery}


async def _emit_incident(spec: IncidentSpec) -> None:
    await create_control_event(
        category=spec.category,
        severity=spec.severity,
        event_type=spec.event_type,
        title=spec.title,
        message=spec.message,
        entity_type=spec.entity_type,
        entity_id=spec.entity_id,
        payload=spec.payload,
        dedupe_key=spec.dedupe_key,
    )


async def _emit_recovery(spec: RecoverySpec) -> None:
    event = await create_control_event(
        category=spec.category,
        severity="INFO",
        event_type=spec.event_type,
        title=spec.title,
        message=spec.message,
        entity_type=spec.entity_type,
        entity_id=spec.entity_id,
        payload=spec.payload,
        dedupe_key=spec.recovery_dedupe_key,
        resolve_dedupe_key=spec.incident_dedupe_key,
        cooldown_seconds=0,
    )
    if event is not None:
        await _mark_event_resolved(int(event.id))


async def emit_control_error_triggers(*, now_utc: datetime | None = None) -> dict[str, int]:
    now_utc = now_utc or utcnow()
    service_statuses, node_snapshots, user_inputs = await asyncio.gather(
        load_monitored_service_statuses(),
        get_server_snapshots(force_refresh=True),
        _load_user_repair_inputs(),
    )
    users, device_counts = user_inputs

    service_incidents, service_recoveries = build_service_incident_specs(service_statuses)
    node_incidents, node_recoveries = build_node_incident_specs(node_snapshots)
    user_incidents, user_recoveries = build_user_incident_specs(users, device_counts, now_utc=now_utc)

    incidents = [*service_incidents, *node_incidents, *user_incidents]
    recoveries = {**service_recoveries, **node_recoveries, **user_recoveries}

    for spec in incidents:
        await _emit_incident(spec)

    active_keys = {spec.dedupe_key for spec in incidents}
    healthy_keys = [key for key in recoveries.keys() if key not in active_keys]
    unresolved_healthy_keys = await _list_unresolved_incident_keys(healthy_keys)
    for dedupe_key in sorted(unresolved_healthy_keys):
        recovery_spec = recoveries.get(dedupe_key)
        if recovery_spec is None:
            continue
        await _emit_recovery(recovery_spec)

    return {
        "service_incidents": len(service_incidents),
        "node_incidents": len(node_incidents),
        "user_incidents": len(user_incidents),
        "recoveries": len(unresolved_healthy_keys),
    }
