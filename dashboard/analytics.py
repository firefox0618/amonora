"""
Расширенная аналитика дашборда Amonora.

Новый слой метрик с:
- Фильтрами по времени
- Сравнением с прошлым периодом
- Процентами и долями
- Детализацией по пользователям, устройствам, платежам, серверам
"""

import copy
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import async_session
from backend.core.models import User, VpnClient
from bot.utils.access import (
    get_access_expires_at_from_user,
    get_access_status_from_user,
    has_active_access_from_user,
)
from bot.utils.regions import normalize_country_code
from dashboard.models import PaymentRecord

DASHBOARD_TIMEZONE = ZoneInfo("Asia/Yekaterinburg")

# Периоды
_PERIOD_PRESETS = {
    "today": lambda now: (now.replace(hour=0, minute=0, second=0, microsecond=0), now),
    "yesterday": lambda now: (
        (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0),
        (now - timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=999999),
    ),
    "7d": lambda now: (now - timedelta(days=7), now),
    "30d": lambda now: (now - timedelta(days=30), now),
    "this_month": lambda now: (now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), now),
    "last_month": lambda now: (
        (now.replace(day=1) - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0),
        (now.replace(day=1) - timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=999999),
    ),
}

_RUNTIME_ANALYTICS_CACHE: dict[str, dict] = {
    "period_metrics": {"expires_at": 0.0, "value": None},
}
_ANALYTICS_CACHE_TTL = 20.0


def _now_ekb() -> datetime:
    return datetime.now(DASHBOARD_TIMEZONE).replace(tzinfo=None)


def _parse_period(period_key: str) -> tuple[datetime, datetime]:
    """Вернуть (start, end) для периода — naive datetime для БД."""
    now = _now_ekb()
    if period_key in _PERIOD_PRESETS:
        return _PERIOD_PRESETS[period_key](now)
    
    # Произвольный диапазон: 2024-01-01..2024-01-31
    try:
        parts = period_key.split("..")
        if len(parts) == 2:
            start = datetime.fromisoformat(parts[0]).replace(tzinfo=None)
            end = datetime.fromisoformat(parts[1]).replace(tzinfo=None, hour=23, minute=59, second=59)
            return start, end
    except (ValueError, AttributeError):
        pass
    
    # По умолчанию — 30 дней
    return _PERIOD_PRESETS["30d"](now)


def _previous_period(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """Вернуть аналогичный предыдущий период."""
    duration = end - start
    prev_start = start - duration
    prev_end = start
    return prev_start, prev_end


def _calc_change(current: int | float, previous: int | float) -> dict:
    """Рассчитать изменение."""
    if previous == 0:
        return {
            "change": current,
            "change_percent": 100.0 if current > 0 else 0.0,
            "direction": "up" if current > 0 else "same",
        }
    
    change = current - previous
    change_percent = round((change / previous) * 100, 1)
    direction = "up" if change > 0 else ("down" if change < 0 else "same")
    
    return {
        "change": change,
        "change_percent": change_percent,
        "direction": direction,
    }


def _calc_percentage_change(current_percent: float, previous_percent: float) -> dict:
    """Изменение в процентных пунктах."""
    change_pp = round(current_percent - previous_percent, 1)
    direction = "up" if change_pp > 0 else ("down" if change_pp < 0 else "same")
    
    return {
        "change_pp": change_pp,
        "current_percent": current_percent,
        "previous_percent": previous_percent,
        "direction": direction,
    }


def _safe_percent(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100, 1)


async def _query_users_in_period(session: AsyncSession, start: datetime, end: datetime) -> list[User]:
    """Пользователи, созданные в периоде."""
    result = await session.execute(
        select(User).where(
            User.created_at >= start,
            User.created_at <= end,
        ).order_by(User.created_at.desc())
    )
    return list(result.scalars().all())


async def _query_payments_in_period(session: AsyncSession, start: datetime, end: datetime) -> list[PaymentRecord]:
    """Платежи, созданные в периоде."""
    result = await session.execute(
        select(PaymentRecord).where(
            PaymentRecord.created_at >= start,
            PaymentRecord.created_at <= end,
        ).order_by(PaymentRecord.created_at.desc())
    )
    return list(result.scalars().all())


async def _query_devices_in_period(session: AsyncSession, start: datetime, end: datetime) -> list[VpnClient]:
    """Устройства, созданные в периоде."""
    result = await session.execute(
        select(VpnClient).where(
            VpnClient.created_at >= start,
            VpnClient.created_at <= end,
        ).order_by(VpnClient.created_at.desc())
    )
    return list(result.scalars().all())


async def calculate_period_metrics(period_key: str = "30d") -> dict:
    """
    Рассчитать все метрики за выбранный период с сравнением с прошлым периодом.
    
    Возвращает полный словарь метрик для дашборда.
    """
    start, end = _parse_period(period_key)
    prev_start, prev_end = _previous_period(start, end)
    
    async with async_session() as session:
        # Все пользователи и платежи для общего контекста
        all_users_result = await session.execute(select(User))
        all_users = all_users_result.scalars().all()
        
        all_clients_result = await session.execute(select(VpnClient))
        all_clients = all_clients_result.scalars().all()
        
        # Пользователи за период
        period_users = await _query_users_in_period(session, start, end)
        prev_users = await _query_users_in_period(session, prev_start, prev_end)
        
        # Платежи за период
        period_payments = await _query_payments_in_period(session, start, end)
        prev_payments = await _query_payments_in_period(session, prev_start, prev_end)
        
        # Устройства за период
        period_devices = await _query_devices_in_period(session, start, end)
        prev_devices = await _query_devices_in_period(session, prev_start, prev_end)
    
    # === БЛОК 1: ПОЛЬЗОВАТЕЛИ ===
    user_metrics = _calculate_user_metrics(all_users, period_users, prev_users)
    
    # === БЛОК 2: УСТРОЙСТВА ===
    device_metrics = _calculate_device_metrics(all_clients, period_devices, prev_devices, all_users)
    
    # === БЛОК 3: ПЛАТЕЖИ ===
    payment_metrics = _calculate_payment_metrics(
        period_payments, prev_payments, all_users, period_users
    )
    
    # === ОБЩИЕ МЕТРИКИ ===
    total_users = len(all_users)
    total_devices = len(all_clients)
    active_access = sum(1 for u in all_users if has_active_access_from_user(u))
    active_paid = sum(1 for u in all_users if get_access_status_from_user(u) == "paid_active")
    active_trials = sum(1 for u in all_users if get_access_status_from_user(u) == "trial_active")
    blocked_users = sum(1 for u in all_users if getattr(u, "is_blocked", False))
    
    return {
        "period": {
            "key": period_key,
            "start": start.strftime("%Y-%m-%d %H:%M"),
            "end": end.strftime("%Y-%m-%d %H:%M"),
            "prev_start": prev_start.strftime("%Y-%m-%d %H:%M"),
            "prev_end": prev_end.strftime("%Y-%m-%d %H:%M"),
            "label": _period_label(period_key),
        },
        "summary": {
            "total_users": total_users,
            "active_access": active_access,
            "active_paid": active_paid,
            "active_trials": active_trials,
            "blocked_users": blocked_users,
            "total_devices": total_devices,
            "revenue": payment_metrics["revenue"],
            "revenue_label": payment_metrics["revenue_label"],
        },
        "users": user_metrics,
        "devices": device_metrics,
        "payments": payment_metrics,
    }


def _calculate_user_metrics(
    all_users: list[User],
    period_users: list[User],
    prev_users: list[User],
) -> dict:
    """Метрики пользователей."""
    # Текущий период
    new_users_count = len(period_users)
    trial_users = sum(1 for u in period_users if get_access_status_from_user(u) == "trial_active")
    paid_users = sum(1 for u in period_users if get_access_status_from_user(u) == "paid_active")
    
    # Процент перехода из триала в оплату
    users_ever_on_trial = [u for u in all_users if u.trial_used]
    users_paid_after_trial = sum(
        1 for u in all_users 
        if u.trial_used and get_access_status_from_user(u) == "paid_active"
    )
    trial_to_paid_percent = _safe_percent(users_paid_after_trial, len(users_ever_on_trial))
    
    # Предыдущий период
    prev_new_users_count = len(prev_users)
    
    # Сравнение
    new_users_change = _calc_change(new_users_count, prev_new_users_count)
    
    # Доли от общей базы
    total = len(all_users)
    trial_percent = _safe_percent(
        sum(1 for u in all_users if get_access_status_from_user(u) == "trial_active"),
        total
    )
    paid_percent = _safe_percent(
        sum(1 for u in all_users if get_access_status_from_user(u) == "paid_active"),
        total
    )
    blocked_percent = _safe_percent(
        sum(1 for u in all_users if getattr(u, "is_blocked", False)),
        total
    )
    
    # Доход на платящего пользователя
    active_paid_count = sum(1 for u in all_users if get_access_status_from_user(u) == "paid_active")
    
    return {
        "new_users": new_users_count,
        "new_users_change": new_users_change,
        "trial_users": trial_users,
        "paid_users": paid_users,
        "trial_to_paid_percent": trial_to_paid_percent,
        "trial_percent": trial_percent,
        "paid_percent": paid_percent,
        "blocked_percent": blocked_percent,
        "active_paid_count": active_paid_count,
    }


def _calculate_device_metrics(
    all_clients: list[VpnClient],
    period_devices: list[VpnClient],
    prev_devices: list[VpnClient],
    all_users: list[User],
) -> dict:
    """Метрики устройств."""
    total = len(all_clients)
    vless_count = sum(1 for c in all_clients if c.protocol == "vless")
    trojan_count = sum(1 for c in all_clients if c.protocol == "trojan")
    
    # За период
    new_devices = len(period_devices)
    prev_new_devices = len(prev_devices)
    new_devices_change = _calc_change(new_devices, prev_new_devices)
    
    # Активные устройства (у пользователей с активным доступом)
    user_map = {u.id: u for u in all_users}
    active_devices = sum(
        1 for c in all_clients
        if (u := user_map.get(c.user_id)) and has_active_access_from_user(u) and not getattr(u, "is_blocked", False)
    )
    
    # Среднее устройств на пользователя
    total_users = len(all_users)
    devices_per_user = round(total / total_users, 2) if total_users > 0 else 0
    
    # Доли
    vless_percent = _safe_percent(vless_count, total)
    trojan_percent = _safe_percent(trojan_count, total)
    
    # Распределение по странам
    country_stats: dict[str, int] = {}
    for client in all_clients:
        import json
        try:
            metadata = json.loads(client.client_data or "{}")
        except json.JSONDecodeError:
            metadata = {}
        country = normalize_country_code(metadata.get("country_code"))
        country_stats[country] = country_stats.get(country, 0) + 1
    
    return {
        "total": total,
        "vless": vless_count,
        "trojan": trojan_count,
        "active_devices": active_devices,
        "new_devices": new_devices,
        "new_devices_change": new_devices_change,
        "devices_per_user": devices_per_user,
        "vless_percent": vless_percent,
        "trojan_percent": trojan_percent,
        "country_stats": country_stats,
    }


def _calculate_payment_metrics(
    period_payments: list[PaymentRecord],
    prev_payments: list[PaymentRecord],
    all_users: list[User],
    period_users: list[User],
) -> dict:
    """Метрики платежей."""
    # Подтверждённые платежи
    confirmed = [p for p in period_payments if p.payment_status == "confirmed"]
    prev_confirmed = [p for p in prev_payments if p.payment_status == "confirmed"]
    
    # Доход
    revenue = sum(p.amount for p in confirmed)
    prev_revenue = sum(p.amount for p in prev_confirmed)
    revenue_change = _calc_change(revenue, prev_revenue)
    
    # Количество оплат
    payment_count = len(confirmed)
    prev_payment_count = len(prev_confirmed)
    payment_count_change = _calc_change(payment_count, prev_payment_count)
    
    # Средний чек
    avg_check = round(revenue / payment_count) if payment_count > 0 else 0
    prev_avg_check = round(prev_revenue / prev_payment_count) if prev_payment_count > 0 else 0
    avg_check_change = _calc_change(avg_check, prev_avg_check)
    
    # Первые оплаты vs продления (нужно анализировать историю пользователя)
    # Упрощённо: если у пользователя это первый подтверждённый платёж — новая оплата
    user_map = {u.id: u for u in all_users}
    
    first_payments = []
    renewals = []
    for payment in confirmed:
        user = user_map.get(payment.user_id)
        if user:
            # Считаем все платежи пользователя до этого
            user_payments_before = [
                p for p in period_payments 
                if p.user_id == payment.user_id and p.created_at < payment.created_at and p.payment_status == "confirmed"
            ]
            if len(user_payments_before) == 0:
                first_payments.append(payment)
            else:
                renewals.append(payment)
    
    first_payment_revenue = sum(p.amount for p in first_payments)
    renewal_revenue = sum(p.amount for p in renewals)
    
    renewal_percent = _safe_percent(len(renewals), payment_count)
    
    # Доход по тарифам
    tariff_revenue: dict[str, dict] = {}
    for payment in confirmed:
        code = payment.tariff_code or "unknown"
        if code not in tariff_revenue:
            tariff_revenue[code] = {"count": 0, "revenue": 0}
        tariff_revenue[code]["count"] += 1
        tariff_revenue[code]["revenue"] += payment.amount
    
    # Популярный тариф
    most_popular_tariff = max(tariff_revenue.items(), key=lambda x: x[1]["count"]) if tariff_revenue else None
    most_revenue_tariff = max(tariff_revenue.items(), key=lambda x: x[1]["revenue"]) if tariff_revenue else None
    
    # Средний доход на платящего пользователя
    unique_paying_users = len(set(p.user_id for p in confirmed))
    revenue_per_user = round(revenue / unique_paying_users) if unique_paying_users > 0 else 0
    
    return {
        "revenue": revenue,
        "revenue_label": _format_rub(revenue),
        "revenue_change": revenue_change,
        "payment_count": payment_count,
        "payment_count_change": payment_count_change,
        "avg_check": avg_check,
        "avg_check_label": _format_rub(avg_check),
        "avg_check_change": avg_check_change,
        "first_payments": len(first_payments),
        "first_payment_revenue": first_payment_revenue,
        "first_payment_revenue_label": _format_rub(first_payment_revenue),
        "renewals": len(renewals),
        "renewal_revenue": renewal_revenue,
        "renewal_revenue_label": _format_rub(renewal_revenue),
        "renewal_percent": renewal_percent,
        "tariff_revenue": tariff_revenue,
        "most_popular_tariff": most_popular_tariff[0] if most_popular_tariff else None,
        "most_revenue_tariff": most_revenue_tariff[0] if most_revenue_tariff else None,
        "revenue_per_user": revenue_per_user,
        "revenue_per_user_label": _format_rub(revenue_per_user),
        "unique_paying_users": unique_paying_users,
    }


def _format_rub(value: int | float | None) -> str:
    if value is None:
        return "—"
    return f"{int(round(value)):,}".replace(",", " ") + " ₽"


def _period_label(period_key: str) -> str:
    labels = {
        "today": "Сегодня",
        "yesterday": "Вчера",
        "7d": "7 дней",
        "30d": "30 дней",
        "this_month": "Этот месяц",
        "last_month": "Прошлый месяц",
    }
    if period_key in labels:
        return labels[period_key]
    # Custom date range
    if ".." in period_key:
        parts = period_key.split("..")
        try:
            from_date = datetime.fromisoformat(parts[0]).strftime("%d.%m.%Y")
            to_date = datetime.fromisoformat(parts[1]).strftime("%d.%m.%Y")
            return f"Произвольно: {from_date} — {to_date}"
        except (ValueError, AttributeError):
            pass
    return period_key
