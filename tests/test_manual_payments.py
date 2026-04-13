import asyncio
from datetime import timedelta

from bot.db import (
    cancel_manual_payment_record,
    create_manual_payment_record,
    get_access_expires_at,
    get_or_create_user,
    get_payment_record_by_id,
    mark_manual_payment_record_submitted,
)
from bot.manual_payments import confirm_manual_payment, reject_manual_payment
from bot.utils.access import utcnow


async def main() -> None:
    user, _ = await get_or_create_user(
        telegram_id=999000111,
        username="manual_payment_test_user",
    )

    record = await create_manual_payment_record(
        user_id=user.id,
        tariff_code="1m",
        payment_method="sbp_manual",
        amount=149,
        currency="RUB",
        duration_days=30,
        note="Smoke request",
        metadata={"tariff_title": "1 месяц"},
    )
    print("Created status:", record.payment_status)

    submitted = await mark_manual_payment_record_submitted(record.id, reference="SMOKE-SBP-001", note="Перевод отмечен")
    print("Submitted status:", submitted.payment_status if submitted else "missing")

    confirmed = await confirm_manual_payment(
        record.id,
        reviewer_actor_id="test:confirm",
        reviewer_actor_name="Test Confirm",
    )
    confirmed_record = await get_payment_record_by_id(record.id)
    print("Confirmed status:", confirmed_record.payment_status if confirmed_record else "missing")
    expires_at = await get_access_expires_at(user.id)
    print("Expires after confirm:", expires_at)
    print("Confirm result exists:", confirmed is not None)

    second = await create_manual_payment_record(
        user_id=user.id,
        tariff_code="3m",
        payment_method="crypto_manual",
        amount=399,
        currency="RUB",
        duration_days=90,
        note="Reject request",
        metadata={"tariff_title": "3 месяца"},
    )
    await mark_manual_payment_record_submitted(second.id, reference="SMOKE-CRYPTO-002", note="Отправлен hash")
    await reject_manual_payment(
        second.id,
        reviewer_actor_id="test:reject",
        reviewer_actor_name="Test Reject",
        reason="Smoke reject",
    )
    rejected_record = await get_payment_record_by_id(second.id)
    print("Rejected status:", rejected_record.payment_status if rejected_record else "missing")
    print("Rejected reason:", rejected_record.rejection_reason if rejected_record else "missing")

    third = await create_manual_payment_record(
        user_id=user.id,
        tariff_code="1m",
        payment_method="sbp_manual",
        amount=149,
        currency="RUB",
        duration_days=30,
        note="Cancel request",
        metadata={"tariff_title": "1 месяц"},
    )
    await cancel_manual_payment_record(third.id)
    cancelled_record = await get_payment_record_by_id(third.id)
    print("Cancelled status:", cancelled_record.payment_status if cancelled_record else "missing")

    expired = await create_manual_payment_record(
        user_id=user.id,
        tariff_code="6m",
        payment_method="crypto_manual",
        amount=699,
        currency="RUB",
        duration_days=180,
        note="Expired request",
        metadata={"tariff_title": "6 месяцев"},
        expires_at=utcnow() - timedelta(minutes=5),
    )
    expired_record = await get_payment_record_by_id(expired.id)
    print("Expired status:", expired_record.payment_status if expired_record else "missing")
    print("Expired reason:", expired_record.rejection_reason if expired_record else "missing")


if __name__ == "__main__":
    asyncio.run(main())
