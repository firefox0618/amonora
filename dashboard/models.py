from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class DashboardAdmin(Base):
    __tablename__ = "dashboard_admins"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="support_admin")
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class DashboardSession(Base):
    __tablename__ = "dashboard_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("dashboard_admins.id"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class DashboardLoginCode(Base):
    __tablename__ = "dashboard_login_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    admin_id: Mapped[int] = mapped_column(ForeignKey("dashboard_admins.id"), index=True, nullable=False)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    bot_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class DashboardAuthLockoutState(Base):
    __tablename__ = "dashboard_auth_lockout_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    identity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    identity_value: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_failure_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class DashboardRolePermissionOverride(Base):
    __tablename__ = "dashboard_role_permission_overrides"

    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ManagedServer(Base):
    __tablename__ = "managed_servers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    country_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    public_ip: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    is_local: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    xui_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bot_service_name: Mapped[str] = mapped_column(String(100), default="amonora-bot.service", nullable=False)
    support_bot_service_name: Mapped[str] = mapped_column(
        String(100),
        default="amonora-support-bot.service",
        nullable=False,
    )
    dashboard_service_name: Mapped[str] = mapped_column(
        String(100),
        default="amonora-dashboard.service",
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class DashboardAuditLog(Base):
    __tablename__ = "dashboard_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("dashboard_admins.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(150), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class PaymentRecord(Base):
    __tablename__ = "payment_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by_admin_id: Mapped[int | None] = mapped_column(ForeignKey("dashboard_admins.id"), nullable=True)
    external_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tariff_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payment_method: Mapped[str] = mapped_column(String(50), nullable=False)
    payment_status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(20), nullable=False, default="RUB")
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_by_actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class FinanceEntry(Base):
    __tablename__ = "finance_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_by_admin_id: Mapped[int | None] = mapped_column(ForeignKey("dashboard_admins.id"), nullable=True)
    counterparty_admin_id: Mapped[int | None] = mapped_column(ForeignKey("dashboard_admins.id"), nullable=True)
    entry_type: Mapped[str] = mapped_column(String(50), nullable=False, default="expense")
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="operations")
    amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(20), nullable=False, default="RUB")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_server: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    source_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_by_admin_id: Mapped[int | None] = mapped_column(ForeignKey("dashboard_admins.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    period_key: Mapped[str | None] = mapped_column(String(20), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


# ===== Маркетинговые кампании и аналитика =====

class MarketingCampaign(Base):
    __tablename__ = "marketing_campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    token: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    cta_label: Mapped[str] = mapped_column(String(255), default="Попробовать бесплатно", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_admin_id: Mapped[int | None] = mapped_column(ForeignKey("dashboard_admins.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    @property
    def tracking_url(self) -> str:
        return f"https://t.me/amonora_bot?start={self.token}"


class CampaignEvent(Base):
    __tablename__ = "campaign_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_token: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    event_name: Mapped[str] = mapped_column(String(100), nullable=False)
    user_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


# ===== Доска задач =====

TASK_STATUSES = ("backlog", "in_progress", "testing", "done", "deferred")

class TaskBoard(Base):
    __tablename__ = "task_board"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="backlog")
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    color: Mapped[str] = mapped_column(String(10), nullable=False, default="#3b82f6")
    assignee: Mapped[str | None] = mapped_column(String(200), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    checklist: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_admin_id: Mapped[int | None] = mapped_column(ForeignKey("dashboard_admins.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

class TaskComment(Base):
    __tablename__ = "task_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("task_board.id"), index=True, nullable=False)
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("dashboard_admins.id"), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
