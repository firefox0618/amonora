from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from backend.core.database import async_session
from bot.db import clear_payment_record_finance_synced, mark_payment_record_finance_synced
from dashboard.models import FinanceEntry, PaymentRecord


FINANCE_REPORT_SLUG = "generated/finance-report-latest.md"
FINANCE_ENTRY_TYPES = {
    "income",
    "expense",
    "salary",
    "settlement",
    "transfer",
    "adjustment",
}
FINANCE_ENTRY_STATUSES = {"draft", "posted", "cancelled"}
FINANCE_INCOME_TYPES = {"income"}
FINANCE_EXPENSE_TYPES = {"expense", "salary", "settlement", "transfer", "adjustment"}
REVENUE_PAYMENT_METHODS = {"sbp_platega", "crypto_platega"}


def finance_type_label(entry_type: str) -> str:
    labels = {
        "income": "Доход",
        "expense": "Расход",
        "salary": "Зарплата",
        "settlement": "Взаиморасчёт",
        "transfer": "Перевод",
        "adjustment": "Корректировка",
    }
    return labels.get(entry_type, entry_type)


def finance_status_label(status: str) -> str:
    labels = {
        "draft": "Черновик",
        "posted": "Проведено",
        "cancelled": "Отменено",
    }
    return labels.get(status, status)


def period_key_for(value: datetime | None) -> str:
    point = value or datetime.utcnow()
    return point.strftime("%Y-%m")


def finance_signed_amount(entry_type: str, amount: int) -> int:
    if entry_type in FINANCE_INCOME_TYPES:
        return int(amount)
    return -int(amount)


def finance_is_expense(entry_type: str) -> bool:
    return entry_type in FINANCE_EXPENSE_TYPES


def payment_method_counts_as_revenue(method: str | None) -> bool:
    return str(method or "").strip().lower() in REVENUE_PAYMENT_METHODS


def _derive_reviewer_admin_id(record: PaymentRecord) -> int | None:
    if record.created_by_admin_id is not None:
        return record.created_by_admin_id
    raw_value = (record.reviewed_by_actor_id or "").strip()
    if raw_value.startswith("dashboard:"):
        try:
            return int(raw_value.split(":", 1)[1])
        except ValueError:
            return None
    return None


async def sync_income_entry_for_payment_record(record_id: int) -> FinanceEntry | None:
    async with async_session() as session:
        record = (
            await session.execute(select(PaymentRecord).where(PaymentRecord.id == record_id))
        ).scalar_one_or_none()

        entry = (
            await session.execute(
                select(FinanceEntry).where(
                    FinanceEntry.source_type == "payment_record",
                    FinanceEntry.source_id == str(record.id),
                )
            )
        ).scalar_one_or_none()

        if (
            record is None
            or record.payment_status != "confirmed"
            or record.amount <= 0
            or not payment_method_counts_as_revenue(record.payment_method)
        ):
            if entry is not None:
                await session.delete(entry)
                await session.commit()
            await clear_payment_record_finance_synced(record_id)
            return None

        if entry is None:
            entry = FinanceEntry(
                created_by_admin_id=record.created_by_admin_id,
                entry_type="income",
                category="subscription_payment",
                amount=record.amount,
                currency=record.currency or "RUB",
                note=f"Платёж #{record.id} · {record.payment_method}",
                status="posted",
                source_type="payment_record",
                source_id=str(record.id),
                approved_by_admin_id=_derive_reviewer_admin_id(record),
                approved_at=record.confirmed_at or record.reviewed_at or record.created_at,
                period_key=period_key_for(record.confirmed_at or record.created_at),
                occurred_at=record.confirmed_at or record.created_at,
            )
            session.add(entry)
        else:
            entry.entry_type = "income"
            entry.category = "subscription_payment"
            entry.amount = record.amount
            entry.currency = record.currency or "RUB"
            entry.note = f"Платёж #{record.id} · {record.payment_method}"
            entry.status = "posted"
            entry.approved_by_admin_id = _derive_reviewer_admin_id(record)
            entry.approved_at = record.confirmed_at or record.reviewed_at or record.created_at
            entry.period_key = period_key_for(record.confirmed_at or record.created_at)
            entry.occurred_at = record.confirmed_at or record.created_at

        await session.commit()
        await session.refresh(entry)
    await mark_payment_record_finance_synced(record_id, finance_entry_id=getattr(entry, "id", None))
    return entry


async def sync_income_entries_for_confirmed_payments() -> int:
    async with async_session() as session:
        rows = list(
            (
                await session.execute(
                    select(PaymentRecord.id).where(
                        PaymentRecord.payment_status == "confirmed",
                        PaymentRecord.amount > 0,
                    )
                )
            ).scalars().all()
        )

    synced = 0
    for record_id in rows:
        entry = await sync_income_entry_for_payment_record(record_id)
        if entry is not None:
            synced += 1
    return synced


async def list_confirmed_payment_ids_missing_finance(*, limit: int = 50) -> list[int]:
    safe_limit = max(int(limit or 0), 1)
    async with async_session() as session:
        rows = list(
            (
                await session.execute(
                    select(PaymentRecord)
                    .where(
                        PaymentRecord.payment_status == "confirmed",
                        PaymentRecord.amount > 0,
                    )
                    .order_by(PaymentRecord.confirmed_at.asc().nullsfirst(), PaymentRecord.id.asc())
                )
            ).scalars().all()
        )
    missing: list[int] = []
    async with async_session() as session:
        for record in rows:
            if not payment_method_counts_as_revenue(record.payment_method):
                continue
            entry = (
                await session.execute(
                    select(FinanceEntry).where(
                        FinanceEntry.source_type == "payment_record",
                        FinanceEntry.source_id == str(record.id),
                    )
                )
            ).scalar_one_or_none()
            if entry is None:
                missing.append(int(record.id))
            if len(missing) >= safe_limit:
                break
    return missing
