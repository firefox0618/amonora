from __future__ import annotations

import secrets
import string
from datetime import datetime

from sqlalchemy import Select, func, select

from backend.core.database import async_session
from backend.core.models import PromoCode, PromoCodeRedemption, User


PROMO_KIND_DISCOUNT_PERCENT = "discount_percent"
PROMO_KIND_DAYS_CREDIT = "days_credit"
PROMO_KIND_GIFT_DAYS = "gift_days"
GIFT_SUBSCRIPTION_PRODUCT_TYPE = "gift_subscription"
PROMO_CODE_KINDS = {
    PROMO_KIND_DISCOUNT_PERCENT,
    PROMO_KIND_DAYS_CREDIT,
    PROMO_KIND_GIFT_DAYS,
}

PROMO_STATUS_ACTIVE = "active"
PROMO_STATUS_INACTIVE = "inactive"
PROMO_STATUS_EXHAUSTED = "exhausted"

PROMO_REDEMPTION_STATUS_PENDING_DISCOUNT = "pending_discount"
PROMO_REDEMPTION_STATUS_APPLIED = "applied"
PROMO_REDEMPTION_STATUS_CONSUMED = "consumed"


def normalize_promo_code(code: str | None) -> str:
    raw = str(code or "").strip().upper()
    safe = "".join(ch for ch in raw if ch in string.ascii_uppercase + string.digits + "-_")
    return safe[:64]


def apply_discount_percent(amount_rub: int, discount_percent: int) -> int:
    safe_amount = max(int(amount_rub), 0)
    safe_discount = max(min(int(discount_percent), 95), 0)
    if safe_discount <= 0:
        return safe_amount
    discounted = safe_amount - int(round(safe_amount * safe_discount / 100))
    return max(discounted, 1)


async def generate_unique_promo_code(prefix: str = "AMONORA") -> str:
    normalized_prefix = normalize_promo_code(prefix).strip("-_") or "AMONORA"
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(20):
        code = f"{normalized_prefix}-{''.join(secrets.choice(alphabet) for _ in range(8))}"
        async with async_session() as session:
            existing = await session.execute(select(PromoCode.id).where(PromoCode.code == code))
            if existing.scalar_one_or_none() is None:
                return code
    raise ValueError("Не удалось сгенерировать уникальный промокод")


async def create_promo_code(
    *,
    code: str | None,
    kind: str,
    title: str | None,
    description: str | None,
    discount_percent: int | None,
    grant_days: int | None,
    max_redemptions: int = 1,
    created_by_admin_id: int | None = None,
    buyer_user_id: int | None = None,
    payment_record_id: int | None = None,
    expires_at: datetime | None = None,
) -> PromoCode:
    normalized_kind = str(kind or "").strip().lower()
    if normalized_kind not in PROMO_CODE_KINDS:
        raise ValueError("Неизвестный тип промокода")

    normalized_code = normalize_promo_code(code) if code else ""
    if not normalized_code:
        normalized_code = await generate_unique_promo_code("AMONORA")

    safe_discount = max(min(int(discount_percent or 0), 95), 0)
    safe_days = max(int(grant_days or 0), 0)
    safe_uses = max(int(max_redemptions or 1), 1)

    if normalized_kind == PROMO_KIND_DISCOUNT_PERCENT and safe_discount <= 0:
        raise ValueError("Для процентного промокода нужно указать скидку")
    if normalized_kind in {PROMO_KIND_DAYS_CREDIT, PROMO_KIND_GIFT_DAYS} and safe_days <= 0:
        raise ValueError("Для промокода на дни нужно указать количество дней")

    async with async_session() as session:
        existing = await session.execute(select(PromoCode).where(PromoCode.code == normalized_code))
        if existing.scalar_one_or_none() is not None:
            raise ValueError("Такой промокод уже существует")
        promo = PromoCode(
            code=normalized_code,
            kind=normalized_kind,
            title=(str(title or "").strip() or None),
            description=(str(description or "").strip() or None),
            discount_percent=safe_discount if normalized_kind == PROMO_KIND_DISCOUNT_PERCENT else None,
            grant_days=safe_days if normalized_kind in {PROMO_KIND_DAYS_CREDIT, PROMO_KIND_GIFT_DAYS} else 0,
            max_redemptions=safe_uses,
            redeemed_count=0,
            status=PROMO_STATUS_ACTIVE,
            created_by_admin_id=created_by_admin_id,
            buyer_user_id=buyer_user_id,
            payment_record_id=payment_record_id,
            expires_at=expires_at,
        )
        session.add(promo)
        await session.commit()
        await session.refresh(promo)
        return promo


async def get_promo_code_by_code(code: str) -> PromoCode | None:
    normalized = normalize_promo_code(code)
    if not normalized:
        return None
    async with async_session() as session:
        result = await session.execute(select(PromoCode).where(PromoCode.code == normalized))
        return result.scalar_one_or_none()


async def get_promo_code_by_payment_record_id(payment_record_id: int) -> PromoCode | None:
    async with async_session() as session:
        result = await session.execute(select(PromoCode).where(PromoCode.payment_record_id == int(payment_record_id)))
        return result.scalar_one_or_none()


async def list_promo_codes(*, search: str = "", kind_filter: str = "all", status_filter: str = "all") -> list[PromoCode]:
    async with async_session() as session:
        query: Select[tuple[PromoCode]] = select(PromoCode).order_by(PromoCode.created_at.desc(), PromoCode.id.desc())
        if search.strip():
            token = f"%{search.strip().upper()}%"
            query = query.where(
                func.upper(PromoCode.code).like(token)
                | func.upper(func.coalesce(PromoCode.title, "")).like(token)
                | func.upper(func.coalesce(PromoCode.description, "")).like(token)
            )
        if kind_filter not in {"", "all"}:
            query = query.where(PromoCode.kind == str(kind_filter).strip().lower())
        if status_filter not in {"", "all"}:
            query = query.where(PromoCode.status == str(status_filter).strip().lower())
        result = await session.execute(query)
        return list(result.scalars().all())


async def get_user_pending_discount(user_id: int) -> PromoCodeRedemption | None:
    async with async_session() as session:
        result = await session.execute(
            select(PromoCodeRedemption)
            .where(
                PromoCodeRedemption.user_id == int(user_id),
                PromoCodeRedemption.status == PROMO_REDEMPTION_STATUS_PENDING_DISCOUNT,
            )
            .order_by(PromoCodeRedemption.redeemed_at.desc(), PromoCodeRedemption.id.desc())
        )
        return result.scalars().first()


async def consume_pending_discount_redemption(redemption_id: int, *, payment_record_id: int) -> PromoCodeRedemption | None:
    async with async_session() as session:
        result = await session.execute(
            select(PromoCodeRedemption)
            .where(PromoCodeRedemption.id == int(redemption_id))
            .with_for_update()
        )
        redemption = result.scalar_one_or_none()
        if redemption is None:
            return None
        if redemption.status != PROMO_REDEMPTION_STATUS_PENDING_DISCOUNT:
            return redemption
        redemption.status = PROMO_REDEMPTION_STATUS_CONSUMED
        redemption.applied_payment_record_id = int(payment_record_id)
        redemption.applied_at = datetime.utcnow()
        await session.commit()
        await session.refresh(redemption)
        return redemption


async def consume_discount_redemption_from_payment_record(record) -> PromoCodeRedemption | None:
    metadata_json = getattr(record, "metadata_json", None)
    if not metadata_json:
        return None
    try:
        import json

        metadata = json.loads(metadata_json)
    except Exception:
        return None
    redemption_id = int(metadata.get("promo_redemption_id") or 0)
    if redemption_id <= 0:
        return None
    return await consume_pending_discount_redemption(redemption_id, payment_record_id=int(record.id))


async def create_gift_promo_code_for_payment(
    *,
    buyer_user_id: int,
    payment_record_id: int,
    grant_days: int,
    tariff_code: str | None,
    title: str | None = None,
) -> PromoCode:
    async with async_session() as session:
        existing = await session.execute(select(PromoCode).where(PromoCode.payment_record_id == int(payment_record_id)))
        promo = existing.scalar_one_or_none()
        if promo is not None:
            return promo
    resolved_title = str(title or "").strip() or f"Подарок на {max(int(grant_days), 1)} дн."
    return await create_promo_code(
        code=None,
        kind=PROMO_KIND_GIFT_DAYS,
        title=resolved_title,
        description=f"Подарочный код {tariff_code or ''}".strip(),
        discount_percent=None,
        grant_days=max(int(grant_days), 1),
        max_redemptions=1,
        buyer_user_id=buyer_user_id,
        payment_record_id=payment_record_id,
    )


async def redeem_promo_code_for_user(user_id: int, raw_code: str) -> dict:
    from bot.db import activate_paid_subscription, clear_vpn_repair_needed, get_access_expires_at, mark_vpn_repair_needed
    from bot.payment_flow import POST_PAYMENT_ACCESS_INCOMPLETE, POST_PAYMENT_SYNC_FAILED, sync_user_vpn_access_with_single_retry

    code = normalize_promo_code(raw_code)
    if not code:
        return {"ok": False, "error": "Введите корректный промокод"}

    async with async_session() as session:
        promo_result = await session.execute(select(PromoCode).where(PromoCode.code == code).with_for_update())
        promo = promo_result.scalar_one_or_none()
        if promo is None:
            return {"ok": False, "error": "Промокод не найден"}
        if promo.status != PROMO_STATUS_ACTIVE:
            return {"ok": False, "error": "Промокод уже недоступен"}
        if promo.expires_at is not None and promo.expires_at <= datetime.utcnow():
            promo.status = PROMO_STATUS_EXHAUSTED
            await session.commit()
            return {"ok": False, "error": "Срок действия промокода закончился"}
        if int(promo.redeemed_count or 0) >= max(int(promo.max_redemptions or 1), 1):
            promo.status = PROMO_STATUS_EXHAUSTED
            await session.commit()
            return {"ok": False, "error": "Лимит активаций у промокода уже исчерпан"}

        existing_redemption = await session.execute(
            select(PromoCodeRedemption).where(
                PromoCodeRedemption.promo_code_id == int(promo.id),
                PromoCodeRedemption.user_id == int(user_id),
            )
        )
        if existing_redemption.scalar_one_or_none() is not None:
            return {"ok": False, "error": "Этот промокод уже был применён на ваш аккаунт"}

        if promo.kind == PROMO_KIND_DISCOUNT_PERCENT:
            pending = await session.execute(
                select(PromoCodeRedemption).where(
                    PromoCodeRedemption.user_id == int(user_id),
                    PromoCodeRedemption.status == PROMO_REDEMPTION_STATUS_PENDING_DISCOUNT,
                )
            )
            if pending.scalar_one_or_none() is not None:
                return {
                    "ok": False,
                    "error": "У вас уже есть активная скидка. Сначала используйте её при оплате подписки.",
                }
            redemption = PromoCodeRedemption(
                promo_code_id=promo.id,
                user_id=int(user_id),
                status=PROMO_REDEMPTION_STATUS_PENDING_DISCOUNT,
                discount_percent=int(promo.discount_percent or 0),
                granted_days=0,
                note="Скидка ожидает применения при следующей покупке подписки",
            )
            session.add(redemption)
            promo.redeemed_count = int(promo.redeemed_count or 0) + 1
            if promo.redeemed_count >= max(int(promo.max_redemptions or 1), 1):
                promo.status = PROMO_STATUS_EXHAUSTED
            promo.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(redemption)
            return {
                "ok": True,
                "kind": promo.kind,
                "promo_code": promo,
                "redemption": redemption,
                "discount_percent": int(redemption.discount_percent or 0),
            }

        granted_days = max(int(promo.grant_days or 0), 0)
        if granted_days <= 0:
            return {"ok": False, "error": "У промокода не задан срок доступа"}

        redemption = PromoCodeRedemption(
            promo_code_id=promo.id,
            user_id=int(user_id),
            status=PROMO_REDEMPTION_STATUS_APPLIED,
            discount_percent=None,
            granted_days=granted_days,
            note="Подписка продлена по промокоду",
            applied_at=datetime.utcnow(),
        )
        session.add(redemption)
        promo.redeemed_count = int(promo.redeemed_count or 0) + 1
        if promo.redeemed_count >= max(int(promo.max_redemptions or 1), 1):
            promo.status = PROMO_STATUS_EXHAUSTED
        promo.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(redemption)

    payment_source = "gift_promo_code" if promo.kind == PROMO_KIND_GIFT_DAYS else "promo_code_days"
    updated_user = await activate_paid_subscription(
        user_id=int(user_id),
        tariff_code=str(promo.title or promo.code),
        payment_id=f"promo:{code}",
        duration_days=granted_days,
        payment_source=payment_source,
    )
    expires_at = await get_access_expires_at(int(user_id))
    sync_failed = False
    if expires_at is None:
        await mark_vpn_repair_needed(int(user_id), POST_PAYMENT_ACCESS_INCOMPLETE)
    else:
        sync_result = await sync_user_vpn_access_with_single_retry(int(user_id), expires_at)
        sync_failed = bool(sync_result.get("sync_failed"))
        if sync_failed:
            await mark_vpn_repair_needed(int(user_id), POST_PAYMENT_SYNC_FAILED)
        else:
            await clear_vpn_repair_needed(int(user_id))
    return {
        "ok": updated_user is not None,
        "kind": promo.kind,
        "promo_code": promo,
        "redemption": redemption,
        "grant_days": granted_days,
        "expires_at": expires_at,
        "sync_failed": sync_failed,
    }


def promo_kind_label(kind: str) -> str:
    normalized = str(kind or "").strip().lower()
    if normalized == PROMO_KIND_DISCOUNT_PERCENT:
        return "Скидка"
    if normalized == PROMO_KIND_DAYS_CREDIT:
        return "Дни доступа"
    if normalized == PROMO_KIND_GIFT_DAYS:
        return "Подарочный"
    return "Промокод"
