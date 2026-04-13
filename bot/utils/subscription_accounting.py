from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select

from backend.core.database import async_session
from dashboard.models import PaymentRecord
from bot.utils.tariffs import get_tariff


SUBSCRIPTION_TARIFF_CODES = ("1m", "3m", "6m", "12m")
MANUAL_EXTENSION_SOURCES = frozenset({"dashboard_manual"})
MANUAL_ACCESS_SOURCES = frozenset({"dashboard_manual"})
ADMIN_ACCESS_SOURCES = frozenset({"manual_vip", "dashboard_vip", "vip_free", "vip"})


@dataclass(frozen=True)
class SubscriptionPaymentSnapshot:
    payment_records: tuple[PaymentRecord, ...]
    latest_tariff_code: str | None
    latest_tariff_title: str | None
    payment_only_expires_at: datetime | None


def _subscription_payment_rows(records: Iterable[PaymentRecord]) -> list[PaymentRecord]:
    rows: list[PaymentRecord] = []
    for record in records:
        if str(getattr(record, "payment_status", "") or "").strip().lower() != "confirmed":
            continue
        tariff_code = str(getattr(record, "tariff_code", "") or "").strip().lower()
        if tariff_code not in SUBSCRIPTION_TARIFF_CODES:
            continue
        rows.append(record)
    rows.sort(
        key=lambda item: (
            _payment_effective_at(item) or datetime.min,
            int(getattr(item, "id", 0) or 0),
        )
    )
    return rows


def _payment_effective_at(record: PaymentRecord) -> datetime | None:
    return (
        getattr(record, "confirmed_at", None)
        or getattr(record, "reviewed_at", None)
        or getattr(record, "created_at", None)
    )


def build_payment_only_expiry(records: Iterable[PaymentRecord]) -> datetime | None:
    payment_rows = _subscription_payment_rows(records)
    expires_at: datetime | None = None
    for record in payment_rows:
        effective_at = _payment_effective_at(record)
        if effective_at is None:
            continue
        duration_days = int(getattr(record, "duration_days", 0) or 0)
        if duration_days <= 0:
            tariff = get_tariff(str(getattr(record, "tariff_code", "") or "").strip().lower())
            duration_days = int(getattr(tariff, "duration_days", 0) or 0)
        if duration_days <= 0:
            continue
        base_point = effective_at if expires_at is None or expires_at <= effective_at else expires_at
        expires_at = base_point + timedelta(days=duration_days)
    return expires_at


def latest_tariff_title(records: Iterable[PaymentRecord]) -> str | None:
    payment_rows = _subscription_payment_rows(records)
    if not payment_rows:
        return None
    latest_record = payment_rows[-1]
    tariff = get_tariff(str(getattr(latest_record, "tariff_code", "") or "").strip().lower())
    if tariff is None:
        return None
    return str(getattr(tariff, "title", "") or "").strip() or None


def manual_extension_days(
    actual_expires_at: datetime | None,
    payment_only_expires_at: datetime | None,
    *,
    threshold_hours: int = 12,
) -> int:
    if actual_expires_at is None or payment_only_expires_at is None:
        return 0
    delta_seconds = (actual_expires_at - payment_only_expires_at).total_seconds()
    if delta_seconds < max(int(threshold_hours), 1) * 3600:
        return 0
    return max(1, round(delta_seconds / 86400))


def _pluralize_days(days: int) -> str:
    value = abs(int(days))
    tail_100 = value % 100
    tail_10 = value % 10
    if 11 <= tail_100 <= 14:
        return "дней"
    if tail_10 == 1:
        return "день"
    if 2 <= tail_10 <= 4:
        return "дня"
    return "дней"


def humanize_extension_duration(days: int) -> str:
    safe_days = max(int(days), 0)
    month_map = {
        30: "1 месяц",
        60: "2 месяца",
        90: "3 месяца",
        120: "4 месяца",
        150: "5 месяцев",
        180: "6 месяцев",
        210: "7 месяцев",
        240: "8 месяцев",
        270: "9 месяцев",
        300: "10 месяцев",
        330: "11 месяцев",
        360: "12 месяцев",
        365: "12 месяцев",
    }
    if safe_days in month_map:
        return month_map[safe_days]
    return f"{safe_days} {_pluralize_days(safe_days)}"


async def load_subscription_payment_snapshot(user_id: int) -> SubscriptionPaymentSnapshot:
    async with async_session() as session:
        rows = list(
            (
                await session.execute(
                    select(PaymentRecord)
                    .where(
                        PaymentRecord.user_id == int(user_id),
                        PaymentRecord.payment_status == "confirmed",
                        PaymentRecord.tariff_code.in_(SUBSCRIPTION_TARIFF_CODES),
                    )
                    .order_by(PaymentRecord.confirmed_at.asc(), PaymentRecord.created_at.asc(), PaymentRecord.id.asc())
                )
            ).scalars().all()
        )
    payment_rows = tuple(_subscription_payment_rows(rows))
    return SubscriptionPaymentSnapshot(
        payment_records=payment_rows,
        latest_tariff_code=str(getattr(payment_rows[-1], "tariff_code", "") or "").strip().lower() if payment_rows else None,
        latest_tariff_title=latest_tariff_title(payment_rows),
        payment_only_expires_at=build_payment_only_expiry(payment_rows),
    )
