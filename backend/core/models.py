from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    preferred_mode: Mapped[str | None] = mapped_column(String(20), default="stable", nullable=True)
    preferred_protocol: Mapped[str] = mapped_column(String(50), default="vless", nullable=False)

    trial_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trial_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    trial_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    trial_channel_unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    trial_activity_level: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    trial_engaged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    subscription_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    subscription_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    subscription_status: Mapped[str] = mapped_column(String(50), default="inactive", nullable=False)
    subscription_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    vpn_repair_needed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    vpn_repair_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    vpn_repair_marked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    referred_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    ref_code: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    referral_bonus_granted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    referral_earned_total_rub: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    balance_rub: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    balance_reserved_rub: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    referral_balance_migrated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class PublicSubscriptionLink(Base):
    __tablename__ = "public_subscription_links"
    __table_args__ = (
        UniqueConstraint("token", name="uq_public_subscription_links_token"),
        Index("idx_public_subscription_links_user_active", "user_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_feed_accessed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PublicSubscriptionRoute(Base):
    __tablename__ = "public_subscription_routes"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "country_code",
            "slot_index",
            name="uq_public_subscription_routes_user_country_slot",
        ),
        UniqueConstraint("client_uuid", name="uq_public_subscription_routes_client_uuid"),
        UniqueConstraint("email", name="uq_public_subscription_routes_email"),
        Index("idx_public_subscription_routes_user_status", "user_id", "status"),
        Index("idx_public_subscription_routes_country_status", "country_code", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    country_code: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    protocol: Mapped[str] = mapped_column(String(50), nullable=False, default="vless")
    client_uuid: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    xui_client_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class VpnClient(Base):
    __tablename__ = "vpn_clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)

    protocol: Mapped[str] = mapped_column(String(50), nullable=False)
    client_uuid: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    xui_client_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_data: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class VpnClientActivation(Base):
    __tablename__ = "vpn_client_activations"
    __table_args__ = (UniqueConstraint("vpn_client_id", "fingerprint_hash", name="uq_vpn_client_activation_fingerprint"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    vpn_client_id: Mapped[int] = mapped_column(ForeignKey("vpn_clients.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fingerprint_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    device_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    activation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_activated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_activated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class DeviceSlotEntitlement(Base):
    __tablename__ = "device_slot_entitlements"
    __table_args__ = (UniqueConstraint("payment_record_id", name="uq_device_slot_entitlements_payment_record_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    payment_record_id: Mapped[int] = mapped_column(
        ForeignKey("payment_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    slots_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price_rub: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_amount_rub: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(30), index=True, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class VpnRepairEvent(Base):
    __tablename__ = "vpn_repair_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class DeviceCompensationJob(Base):
    __tablename__ = "device_compensation_jobs"
    __table_args__ = (
        Index("idx_device_compensation_jobs_status_next_attempt_at", "status", "next_attempt_at"),
        Index("idx_device_compensation_jobs_dedupe_status", "dedupe_key", "status"),
        Index("idx_device_compensation_jobs_request_id", "request_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    vpn_client_id: Mapped[int | None] = mapped_column(
        ForeignKey("vpn_clients.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class UserDeletionJob(Base):
    __tablename__ = "user_deletion_jobs"
    __table_args__ = (
        Index("idx_user_deletion_jobs_status_updated_at", "status", "updated_at"),
        Index("idx_user_deletion_jobs_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    admin_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    stage: Mapped[str] = mapped_column(String(64), nullable=False, default="created")
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="Неизвестно")
    status: Mapped[str] = mapped_column(String(50), default="new", nullable=False)
    assigned_admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    assigned_admin_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_message_preview: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_user_message_preview: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_admin_reply_preview: Mapped[str] = mapped_column(Text, nullable=False, default="")
    admin_cards_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SupportTicketMessage(Base):
    __tablename__ = "support_ticket_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("support_tickets.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    sender_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sender_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    content_type: Mapped[str] = mapped_column(String(50), nullable=False, default="text")
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    attachment_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attachment_file_unique_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attachment_kind: Mapped[str | None] = mapped_column(String(50), nullable=True)
    attachment_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attachment_mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attachment_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class UserBalanceEvent(Base):
    __tablename__ = "user_balance_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Referral(Base):
    __tablename__ = "referrals"
    __table_args__ = (UniqueConstraint("invited_user_id", name="uq_referrals_invited_user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    referrer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    invited_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ReferralReward(Base):
    __tablename__ = "referral_rewards"
    __table_args__ = (UniqueConstraint("payment_record_id", name="uq_referral_rewards_payment_record_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    referrer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    invited_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    payment_record_id: Mapped[int] = mapped_column(
        ForeignKey("payment_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    tariff_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bonus_referrer_rub: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bonus_invited_rub: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="applied")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class PromoCode(Base):
    __tablename__ = "promo_codes"
    __table_args__ = (
        UniqueConstraint("code", name="uq_promo_codes_code"),
        UniqueConstraint("payment_record_id", name="uq_promo_codes_payment_record_id"),
        Index("idx_promo_codes_status_kind_created_at", "status", "kind", "created_at"),
        Index("idx_promo_codes_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="discount_percent")
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    discount_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grant_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_redemptions: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    redeemed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_by_admin_id: Mapped[int | None] = mapped_column(ForeignKey("dashboard_admins.id"), nullable=True, index=True)
    buyer_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    payment_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class PromoCodeRedemption(Base):
    __tablename__ = "promo_code_redemptions"
    __table_args__ = (
        UniqueConstraint("promo_code_id", "user_id", name="uq_promo_code_redemptions_user"),
        Index("idx_promo_code_redemptions_user_status", "user_id", "status"),
        Index("idx_promo_code_redemptions_promo_status", "promo_code_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    promo_code_id: Mapped[int] = mapped_column(ForeignKey("promo_codes.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="applied")
    discount_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    granted_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    applied_payment_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    redeemed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ControlNotificationEvent(Base):
    __tablename__ = "control_notification_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    repeat_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ControlAdminNotificationPreference(Base):
    __tablename__ = "control_admin_notification_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ControlMessageTemplate(Base):
    __tablename__ = "control_message_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    buttons_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ControlTriggerRule(Base):
    __tablename__ = "control_trigger_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    family: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    buttons_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ControlBroadcastCampaign(Base):
    __tablename__ = "control_broadcast_campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    status: Mapped[str] = mapped_column(String(50), index=True, nullable=False, default="draft")
    audience_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    priority_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    message_body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    buttons_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("control_message_templates.id"), nullable=True)
    trigger_rule_id: Mapped[int | None] = mapped_column(ForeignKey("control_trigger_rules.id"), nullable=True)
    is_test: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    target_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clicked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    converted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ControlBroadcastDelivery(Base):
    __tablename__ = "control_broadcast_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("control_broadcast_campaigns.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    bot_key: Mapped[str] = mapped_column(String(20), nullable=False, default="bot")
    status: Mapped[str] = mapped_column(String(30), index=True, nullable=False, default="queued")
    cta_action: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    converted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ControlTriggerDeliveryLog(Base):
    __tablename__ = "control_trigger_delivery_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    trigger_rule_id: Mapped[int | None] = mapped_column(ForeignKey("control_trigger_rules.id"), nullable=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("control_broadcast_campaigns.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    event_key: Mapped[str] = mapped_column(String(120), nullable=False)
    dedupe_key: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    result: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ChannelContentItem(Base):
    __tablename__ = "channel_content_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_type: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    topic_brief: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(30), index=True, nullable=False, default="queued")
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    cta_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    deep_link_token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ChannelPostTouch(Base):
    __tablename__ = "channel_post_touches"
    __table_args__ = (UniqueConstraint("item_id", "user_id", name="uq_channel_post_touch_item_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("channel_content_items.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    converted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    conversion_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)


class AnalyticsUserAttribution(Base):
    __tablename__ = "analytics_user_attribution"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_analytics_user_attribution_user_id"),
        Index("idx_analytics_user_attribution_first_source", "first_source_type", "first_source_key", "first_seen_at"),
        Index("idx_analytics_user_attribution_last_source", "last_source_type", "last_source_key", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    first_source_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    first_source_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    first_channel_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("channel_content_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_source_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    last_source_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    last_channel_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("channel_content_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_analytics_events_dedupe_key"),
        Index("idx_analytics_events_name_occurred_at", "event_name", "occurred_at"),
        Index("idx_analytics_events_user_occurred_at", "user_id", "occurred_at"),
        Index("idx_analytics_events_channel_item_occurred_at", "channel_item_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    event_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_record_id: Mapped[int | None] = mapped_column(ForeignKey("payment_records.id", ondelete="SET NULL"), nullable=True, index=True)
    vpn_client_id: Mapped[int | None] = mapped_column(ForeignKey("vpn_clients.id", ondelete="SET NULL"), nullable=True, index=True)
    channel_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("channel_content_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tariff_code: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    country_code: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AnalyticsDailyStageCount(Base):
    __tablename__ = "analytics_daily_stage_counts"
    __table_args__ = (
        UniqueConstraint(
            "bucket_date",
            "event_name",
            "source_mode",
            "source_type",
            "source_key",
            "channel_item_id",
            name="uq_analytics_daily_stage_counts_bucket",
        ),
        Index("idx_analytics_daily_stage_counts_bucket_event", "bucket_date", "event_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bucket_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    event_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="first")
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="organic_bot")
    source_key: Mapped[str] = mapped_column(String(255), nullable=False, default="organic_bot")
    channel_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("channel_content_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    content_type: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    events_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    users_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AnalyticsDailyRevenue(Base):
    __tablename__ = "analytics_daily_revenue"
    __table_args__ = (
        UniqueConstraint(
            "bucket_date",
            "source_mode",
            "source_type",
            "source_key",
            "channel_item_id",
            "tariff_code",
            "payment_method",
            "payment_kind",
            name="uq_analytics_daily_revenue_bucket",
        ),
        Index("idx_analytics_daily_revenue_bucket", "bucket_date", "payment_method"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bucket_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="first")
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="organic_bot")
    source_key: Mapped[str] = mapped_column(String(255), nullable=False, default="organic_bot")
    channel_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("channel_content_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    content_type: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    tariff_code: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    payment_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown", index=True)
    payments_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revenue_amount_rub: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AnalyticsDailyStageSegment(Base):
    __tablename__ = "analytics_daily_stage_segments"
    __table_args__ = (
        UniqueConstraint(
            "bucket_date",
            "event_name",
            "source_mode",
            "source_type",
            "source_key",
            "channel_item_id",
            "user_segment",
            name="uq_analytics_daily_stage_segments_bucket",
        ),
        Index("idx_analytics_daily_stage_segments_bucket_event", "bucket_date", "event_name", "user_segment"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bucket_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    event_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="first")
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="organic_bot")
    source_key: Mapped[str] = mapped_column(String(255), nullable=False, default="organic_bot")
    channel_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("channel_content_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    content_type: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    user_segment: Mapped[str] = mapped_column(String(20), nullable=False, default="returning", index=True)
    events_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    users_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AnalyticsDailyRevenueSegment(Base):
    __tablename__ = "analytics_daily_revenue_segments"
    __table_args__ = (
        UniqueConstraint(
            "bucket_date",
            "source_mode",
            "source_type",
            "source_key",
            "channel_item_id",
            "tariff_code",
            "payment_method",
            "payment_kind",
            "user_segment",
            name="uq_analytics_daily_revenue_segments_bucket",
        ),
        Index("idx_analytics_daily_revenue_segments_bucket", "bucket_date", "payment_method", "user_segment"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bucket_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="first")
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="organic_bot")
    source_key: Mapped[str] = mapped_column(String(255), nullable=False, default="organic_bot")
    channel_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("channel_content_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    content_type: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    tariff_code: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    payment_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown", index=True)
    user_segment: Mapped[str] = mapped_column(String(20), nullable=False, default="returning", index=True)
    payments_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revenue_amount_rub: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AnalyticsDailyConnection(Base):
    __tablename__ = "analytics_daily_connection"
    __table_args__ = (
        UniqueConstraint(
            "bucket_date",
            "source_mode",
            "source_type",
            "source_key",
            "channel_item_id",
            "country_code",
            name="uq_analytics_daily_connection_bucket",
        ),
        Index("idx_analytics_daily_connection_bucket", "bucket_date", "country_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bucket_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="first")
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="organic_bot")
    source_key: Mapped[str] = mapped_column(String(255), nullable=False, default="organic_bot")
    channel_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("channel_content_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    content_type: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    country_code: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    config_issued_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config_issue_failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_connection_success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    connection_failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_first_connection_lag_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AnalyticsDailyPaymentFailureReason(Base):
    __tablename__ = "analytics_daily_payment_failure_reasons"
    __table_args__ = (
        UniqueConstraint(
            "bucket_date",
            "source_mode",
            "source_type",
            "source_key",
            "channel_item_id",
            "payment_method",
            "reason_key",
            name="uq_analytics_daily_payment_failure_reasons_bucket",
        ),
        Index(
            "idx_analytics_daily_payment_failure_reasons_bucket",
            "bucket_date",
            "payment_method",
            "reason_key",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bucket_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="first")
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="organic_bot")
    source_key: Mapped[str] = mapped_column(String(255), nullable=False, default="organic_bot")
    channel_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("channel_content_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    content_type: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    reason_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    failures_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AnalyticsDailyAttributionIntegrity(Base):
    __tablename__ = "analytics_daily_attribution_integrity"
    __table_args__ = (
        UniqueConstraint(
            "bucket_date",
            "issue_type",
            name="uq_analytics_daily_attribution_integrity_bucket",
        ),
        Index(
            "idx_analytics_daily_attribution_integrity_bucket",
            "bucket_date",
            "issue_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bucket_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    issue_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    affected_users_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_bot_start_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AnalyticsCohortRetention(Base):
    __tablename__ = "analytics_cohort_retention"
    __table_args__ = (
        UniqueConstraint("cohort_type", "cohort_date", "period_days", name="uq_analytics_cohort_retention_bucket"),
        Index("idx_analytics_cohort_retention_type_date", "cohort_type", "cohort_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cohort_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    cohort_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cohort_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    connected_users: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    converted_users: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    renewed_users: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expired_users: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_users: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AnalyticsRefreshState(Base):
    __tablename__ = "analytics_refresh_state"

    state_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    cursor_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AnalyticsHourlyOpsIncident(Base):
    __tablename__ = "analytics_hourly_ops_incidents"
    __table_args__ = (
        UniqueConstraint(
            "bucket_hour",
            "incident_class",
            "category",
            "severity",
            "event_type",
            name="uq_analytics_hourly_ops_incidents_bucket",
        ),
        Index("idx_analytics_hourly_ops_incidents_bucket", "bucket_hour", "severity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bucket_hour: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    incident_class: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resolved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    repeated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_entities_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AnalyticsHourlyOpsSnapshot(Base):
    __tablename__ = "analytics_hourly_ops_snapshots"
    __table_args__ = (
        UniqueConstraint("bucket_hour", name="uq_analytics_hourly_ops_snapshots_bucket"),
        Index("idx_analytics_hourly_ops_snapshots_bucket", "bucket_hour"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bucket_hour: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    repair_needed_open_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unresolved_incident_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unresolved_warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unresolved_critical_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unresolved_access_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unresolved_node_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unresolved_service_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provisioning_failure_events_24h: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reconcile_failure_events_24h: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AnalyticsRuntimeStatus(Base):
    __tablename__ = "analytics_runtime_status"
    __table_args__ = (
        Index("idx_analytics_runtime_status_group_updated_at", "status_group", "updated_at"),
    )

    status_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    status_group: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status_value: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class DailyNewsReviewItem(Base):
    __tablename__ = "daily_news_review_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_provider: Mapped[str | None] = mapped_column(String(120), nullable=True)
    topic_key: Mapped[str | None] = mapped_column(String(500), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(30), index=True, nullable=False, default="pending")
    post_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_requested_at: Mapped[datetime | None] = mapped_column(DateTime, index=True, nullable=True)
    review_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
