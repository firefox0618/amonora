"""
Сервис маркетинговых кампаний и аналитики.

Управление трекинг-кампаниями, статистика, воронка конверсии.
"""

import secrets
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import async_session
from dashboard.models import CampaignEvent, DashboardAdmin, DashboardAuditLog, MarketingCampaign


async def create_campaign(
    name: str,
    cta_label: str = "Попробовать бесплатно",
    admin: DashboardAdmin | None = None,
    ip_address: str | None = None,
) -> MarketingCampaign:
    """Создать новую трекинг-кампанию."""
    token = f"camp_{secrets.token_hex(8)}_{datetime.now().strftime('%Y%m%d')}"
    
    async with async_session() as session:
        campaign = MarketingCampaign(
            name=name.strip(),
            token=token,
            cta_label=cta_label,
            created_by_admin_id=admin.id if admin else None,
        )
        session.add(campaign)
        
        if admin:
            audit = DashboardAuditLog(
                admin_id=admin.id,
                action="create_campaign",
                target_type="marketing_campaign",
                target_id=str(campaign.id),
                details_text=f"Кампания: {name}, токен: {token}",
                ip_address=ip_address,
            )
            session.add(audit)
        
        await session.commit()
        await session.refresh(campaign)
    
    return campaign


async def list_campaigns(limit: int = 50, offset: int = 0) -> list[dict]:
    """Получить список всех кампаний со статистикой."""
    async with async_session() as session:
        result = await session.execute(
            select(MarketingCampaign)
            .order_by(MarketingCampaign.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        campaigns = result.scalars().all()
    
    result_list = []
    for campaign in campaigns:
        stats = await get_campaign_stats(campaign.token)
        result_list.append({
            "id": campaign.id,
            "name": campaign.name,
            "token": campaign.token,
            "cta_label": campaign.cta_label,
            "is_active": campaign.is_active,
            "tracking_url": campaign.tracking_url,
            "created_at": campaign.created_at.strftime("%Y-%m-%d %H:%M") if campaign.created_at else "",
            "stats": stats,
        })
    
    return result_list


async def get_campaign_detail(campaign_id: int) -> dict | None:
    """Получить детальную статистику по кампании."""
    async with async_session() as session:
        result = await session.execute(
            select(MarketingCampaign).where(MarketingCampaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
    
    if campaign is None:
        return None
    
    stats = await get_campaign_stats(campaign.token)
    funnel = await get_funnel_data(campaign.token)
    
    # Recent events
    async with async_session() as session:
        events_result = await session.execute(
            select(CampaignEvent)
            .where(CampaignEvent.campaign_token == campaign.token)
            .order_by(CampaignEvent.created_at.desc())
            .limit(50)
        )
        events = events_result.scalars().all()
    
    events_list = []
    for event in events:
        events_list.append({
            "event_name": event.event_name,
            "user_telegram_id": event.user_telegram_id,
            "created_at": event.created_at.strftime("%Y-%m-%d %H:%M") if event.created_at else "",
        })
    
    return {
        "id": campaign.id,
        "name": campaign.name,
        "token": campaign.token,
        "cta_label": campaign.cta_label,
        "is_active": campaign.is_active,
        "tracking_url": campaign.tracking_url,
        "created_at": campaign.created_at.strftime("%Y-%m-%d %H:%M") if campaign.created_at else "",
        "stats": stats,
        "funnel": funnel,
        "recent_events": events_list,
    }


async def get_campaign_stats(token: str) -> dict:
    """Получить статистику по токену кампании."""
    async with async_session() as session:
        # Переходы по ссылке (event: link_clicked)
        transitions_result = await session.execute(
            select(func.count(CampaignEvent.id)).where(
                CampaignEvent.campaign_token == token,
                CampaignEvent.event_name == "link_clicked",
            )
        )
        transitions = transitions_result.scalar() or 0
        
        # События по типам
        events_result = await session.execute(
            select(CampaignEvent.event_name, func.count(CampaignEvent.id))
            .where(CampaignEvent.campaign_token == token)
            .group_by(CampaignEvent.event_name)
        )
        events = dict(events_result.all())
    
    bot_starts = events.get("bot_start", 0)
    trial_started = events.get("trial_started", 0)
    key_issued = events.get("config_issued", 0) + events.get("connection_ready", 0)
    
    # Оплаты — считаем подтверждённые платежи пользователей из кампании
    paid = events.get("payment_confirmed", 0)
    renewed = events.get("subscription_renewed", 0)
    
    conversion_rate = 0.0
    if transitions > 0:
        conversion_rate = round((paid / transitions) * 100, 2)
    
    return {
        "transitions": transitions,
        "bot_starts": bot_starts,
        "trial_started": trial_started,
        "key_issued": key_issued,
        "paid": paid,
        "renewed": renewed,
        "conversion_rate": conversion_rate,
    }


async def get_funnel_data(token: str) -> list[dict]:
    """Получить данные воронки конверсии."""
    stats = await get_campaign_stats(token)
    
    funnel = [
        {"stage": "Переход по ссылке", "count": stats["transitions"], "rate": 100.0},
        {"stage": "Нажали /start", "count": stats["bot_starts"], "rate": 0.0},
        {"stage": "Начали триал", "count": stats["trial_started"], "rate": 0.0},
        {"stage": "Получили ключ", "count": stats["key_issued"], "rate": 0.0},
        {"stage": "Оплатили", "count": stats["paid"], "rate": stats["conversion_rate"]},
        {"stage": "Продлили", "count": stats["renewed"], "rate": 0.0},
    ]
    
    # Рассчитываем проценты относительно первого этапа
    base = stats["transitions"] or 1
    for i in range(1, len(funnel)):
        funnel[i]["rate"] = round((funnel[i]["count"] / base) * 100, 2)
    
    return funnel


async def record_campaign_event(
    campaign_token: str,
    event_name: str,
    user_telegram_id: int | None = None,
    user_id: int | None = None,
    ip_address: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Записать событие кампании."""
    import json
    
    async with async_session() as session:
        event = CampaignEvent(
            campaign_token=campaign_token,
            event_name=event_name,
            user_telegram_id=user_telegram_id,
            user_id=user_id,
            ip_address=ip_address,
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        session.add(event)
        await session.commit()


async def toggle_campaign_active(campaign_id: int, admin: DashboardAdmin, ip_address: str | None) -> MarketingCampaign | None:
    """Переключить активность кампании."""
    async with async_session() as session:
        result = await session.execute(
            select(MarketingCampaign).where(MarketingCampaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        if campaign is None:
            return None
        
        campaign.is_active = not campaign.is_active
        
        audit = DashboardAuditLog(
            admin_id=admin.id,
            action="toggle_campaign",
            target_type="marketing_campaign",
            target_id=str(campaign_id),
            details_text=f"Активность: {campaign.is_active}",
            ip_address=ip_address,
        )
        session.add(audit)
        await session.commit()
        await session.refresh(campaign)
    
    return campaign


async def delete_campaign(campaign_id: int, admin: DashboardAdmin, ip_address: str | None) -> bool:
    """Удалить кампанию."""
    async with async_session() as session:
        result = await session.execute(
            select(MarketingCampaign).where(MarketingCampaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        if campaign is None:
            return False
        
        # Удалить события
        await session.execute(
            CampaignEvent.__table__.delete().where(CampaignEvent.campaign_token == campaign.token)
        )
        
        # Удалить кампанию
        await session.delete(campaign)
        
        audit = DashboardAuditLog(
            admin_id=admin.id,
            action="delete_campaign",
            target_type="marketing_campaign",
            target_id=str(campaign_id),
            details_text=f"Удалена: {campaign.name}",
            ip_address=ip_address,
        )
        session.add(audit)
        await session.commit()
    
    return True
