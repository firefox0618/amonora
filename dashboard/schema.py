import os
import socket

from sqlalchemy import select

import backend.core.models  # noqa: F401
import dashboard.models  # noqa: F401
from backend.core.database import Base, async_session, engine
from backend.core.schema import CORE_SCHEMA_MIGRATIONS, SchemaMigrationStep, apply_schema_migrations
from bot.config import config
from dashboard.models import DashboardAdmin, ManagedServer
from dashboard.security import hash_password


DASHBOARD_SCHEMA_MIGRATIONS = (
    SchemaMigrationStep(
        "dashboard_001_admin_avatar_path",
        "ALTER TABLE dashboard_admins ADD COLUMN IF NOT EXISTS avatar_path VARCHAR(255) NULL",
    ),
    SchemaMigrationStep(
        "dashboard_002_marketing_campaigns_table",
        """
        CREATE TABLE IF NOT EXISTS marketing_campaigns (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            token VARCHAR(100) UNIQUE NOT NULL,
            cta_label VARCHAR(255) DEFAULT 'Попробовать бесплатно' NOT NULL,
            is_active BOOLEAN DEFAULT TRUE NOT NULL,
            created_by_admin_id INTEGER REFERENCES dashboard_admins(id),
            created_at TIMESTAMP DEFAULT NOW() NOT NULL
        )
        """,
    ),
    SchemaMigrationStep(
        "dashboard_003_marketing_campaigns_token_index",
        "CREATE INDEX IF NOT EXISTS ix_marketing_campaigns_token ON marketing_campaigns(token)",
    ),
    SchemaMigrationStep(
        "dashboard_004_campaign_events_table",
        """
        CREATE TABLE IF NOT EXISTS campaign_events (
            id SERIAL PRIMARY KEY,
            campaign_token VARCHAR(100) NOT NULL,
            event_name VARCHAR(100) NOT NULL,
            user_telegram_id BIGINT NULL,
            user_id INTEGER REFERENCES users(id),
            ip_address VARCHAR(100) NULL,
            metadata_json TEXT NULL,
            created_at TIMESTAMP DEFAULT NOW() NOT NULL
        )
        """,
    ),
    SchemaMigrationStep(
        "dashboard_005_campaign_events_token_index",
        "CREATE INDEX IF NOT EXISTS ix_campaign_events_token ON campaign_events(campaign_token)",
    ),
    SchemaMigrationStep(
        "dashboard_006_campaign_events_name_index",
        "CREATE INDEX IF NOT EXISTS ix_campaign_events_name ON campaign_events(event_name)",
    ),
    SchemaMigrationStep(
        "dashboard_007_task_board_table",
        """
        CREATE TABLE IF NOT EXISTS task_board (
            id SERIAL PRIMARY KEY,
            title VARCHAR(500) NOT NULL,
            description TEXT NULL,
            status VARCHAR(30) DEFAULT 'backlog' NOT NULL,
            created_by_admin_id INTEGER REFERENCES dashboard_admins(id),
            created_at TIMESTAMP DEFAULT NOW() NOT NULL,
            updated_at TIMESTAMP DEFAULT NOW() NOT NULL
        )
        """,
    ),
    SchemaMigrationStep(
        "dashboard_008_task_comments_table",
        """
        CREATE TABLE IF NOT EXISTS task_comments (
            id SERIAL PRIMARY KEY,
            task_id INTEGER REFERENCES task_board(id) ON DELETE CASCADE NOT NULL,
            admin_id INTEGER REFERENCES dashboard_admins(id),
            text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW() NOT NULL
        )
        """,
    ),
    SchemaMigrationStep(
        "dashboard_009_task_comments_task_index",
        "CREATE INDEX IF NOT EXISTS ix_task_comments_task ON task_comments(task_id)",
    ),
    SchemaMigrationStep(
        "dashboard_010_task_board_priority",
        "ALTER TABLE task_board ADD COLUMN IF NOT EXISTS priority VARCHAR(20) DEFAULT 'medium' NOT NULL",
    ),
    SchemaMigrationStep(
        "dashboard_011_task_board_color",
        "ALTER TABLE task_board ADD COLUMN IF NOT EXISTS color VARCHAR(10) DEFAULT '#3b82f6' NOT NULL",
    ),
    SchemaMigrationStep(
        "dashboard_012_task_board_assignee",
        "ALTER TABLE task_board ADD COLUMN IF NOT EXISTS assignee VARCHAR(200) NULL",
    ),
    SchemaMigrationStep(
        "dashboard_013_task_board_due_date",
        "ALTER TABLE task_board ADD COLUMN IF NOT EXISTS due_date TIMESTAMP NULL",
    ),
    SchemaMigrationStep(
        "dashboard_014_task_board_tags",
        "ALTER TABLE task_board ADD COLUMN IF NOT EXISTS tags TEXT NULL",
    ),
    SchemaMigrationStep(
        "dashboard_015_task_board_checklist",
        "ALTER TABLE task_board ADD COLUMN IF NOT EXISTS checklist TEXT NULL",
    ),
)


async def ensure_dashboard_schema() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await apply_schema_migrations(connection, CORE_SCHEMA_MIGRATIONS)
        await apply_schema_migrations(connection, DASHBOARD_SCHEMA_MIGRATIONS)


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is None:
        return None
    return value.strip()


async def seed_dashboard_defaults() -> None:
    owner_username = _env("DASHBOARD_OWNER_USERNAME")
    owner_password = _env("DASHBOARD_OWNER_PASSWORD")
    tech_username = _env("DASHBOARD_TECH_USERNAME")
    tech_password = _env("DASHBOARD_TECH_PASSWORD")
    support_username = _env("DASHBOARD_SUPPORT_USERNAME")
    support_password = _env("DASHBOARD_SUPPORT_PASSWORD")

    admin_specs = [
        {
            "username": owner_username,
            "password": owner_password,
            "display_name": "Rudolf",
            "role": "owner",
            "telegram_id": 7650618403,
        },
        {
            "username": tech_username,
            "password": tech_password,
            "display_name": "Ruslan",
            "role": "tech_admin",
            "telegram_id": 548589949,
        },
        {
            "username": support_username,
            "password": support_password,
            "display_name": "Muradym",
            "role": "support_admin",
            "telegram_id": 5487345316,
        },
    ]

    async with async_session() as session:
        for spec in admin_specs:
            if not spec["username"] or not spec["password"]:
                continue

            existing = await session.execute(
                select(DashboardAdmin).where(DashboardAdmin.username == spec["username"])
            )
            admin = existing.scalar_one_or_none()
            if admin is None:
                admin = DashboardAdmin(
                    username=spec["username"],
                    display_name=spec["display_name"],
                    role=spec["role"],
                    telegram_id=spec["telegram_id"],
                    password_hash=hash_password(spec["password"]),
                )
                session.add(admin)

        existing_local_server = await session.execute(select(ManagedServer).where(ManagedServer.is_local.is_(True)))
        local_server = existing_local_server.scalar_one_or_none()
        server_name = _env("DASHBOARD_PRIMARY_SERVER_NAME", "Amonora Core")
        if local_server is None:
            session.add(
                ManagedServer(
                    name=server_name,
                    country_code=_env("DASHBOARD_PRIMARY_SERVER_COUNTRY_CODE", "eu"),
                    country_name=_env("DASHBOARD_PRIMARY_SERVER_COUNTRY_NAME", "Europe"),
                    host=_env("DASHBOARD_PRIMARY_SERVER_HOST", socket.gethostname()),
                    public_ip=_env("DASHBOARD_PRIMARY_SERVER_IP", "127.0.0.1"),
                    provider=_env("DASHBOARD_PRIMARY_SERVER_PROVIDER", "Amonora Core"),
                    status="active",
                    is_local=True,
                    xui_url=_env("DASHBOARD_PRIMARY_SERVER_XUI_URL"),
                )
            )

        await session.commit()
