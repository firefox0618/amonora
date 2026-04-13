import os
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import text

import backend.core.models  # noqa: F401
import dashboard.models  # noqa: F401
from backend.core.database import Base, engine


_schema_ready = False
SCHEMA_MIGRATION_REGISTRY_TABLE = "schema_migration_steps"


@dataclass(frozen=True)
class SchemaMigrationStep:
    key: str
    statement: str
    verify_query: str | None = None

REQUIRED_SCHEMA_COLUMNS = {
    "users": {
        "is_synthetic",
        "subscription_started_at",
        "subscription_expires_at",
        "subscription_status",
        "trial_channel_unsubscribed_at",
        "trial_activity_level",
        "trial_engaged_at",
        "vpn_repair_needed",
        "vpn_repair_reason",
        "preferred_mode",
        "preferred_protocol",
        "balance_rub",
        "balance_reserved_rub",
        "last_activity_at",
    },
    "vpn_clients": {"xui_client_id", "client_data"},
    "public_subscription_links": {
        "user_id",
        "token",
        "is_active",
        "created_at",
        "updated_at",
        "rotated_at",
        "revoked_at",
        "last_viewed_at",
        "last_feed_accessed_at",
    },
    "public_subscription_routes": {
        "user_id",
        "country_code",
        "slot_index",
        "protocol",
        "client_uuid",
        "email",
        "xui_client_id",
        "client_data",
        "status",
        "created_at",
        "updated_at",
        "disabled_at",
    },
    "vpn_client_activations": {"vpn_client_id", "user_id", "fingerprint_hash"},
    "payment_records": {
        "metadata_json",
        "reviewed_by_actor_id",
        "reviewed_at",
        "expires_at",
        "confirmed_at",
        "balance_reserved_amount",
        "balance_applied_amount",
    },
    "support_tickets": {"user_id", "status", "closed_at"},
    "support_ticket_messages": {"ticket_id", "attachment_file_id", "attachment_kind", "attachment_mime_type"},
    "finance_entries": {"status", "source_type", "source_id", "approved_at", "period_key"},
    "device_slot_entitlements": {"user_id", "payment_record_id", "status", "expires_at"},
    "device_compensation_jobs": {
        "action",
        "status",
        "user_id",
        "vpn_client_id",
        "request_id",
        "dedupe_key",
        "payload_json",
        "attempt_count",
        "last_error",
        "next_attempt_at",
        "locked_at",
        "completed_at",
        "created_at",
        "updated_at",
    },
    "user_deletion_jobs": {
        "user_id",
        "telegram_id",
        "admin_id",
        "status",
        "stage",
        "ip_address",
        "payload_json",
        "last_error",
        "completed_at",
        "created_at",
        "updated_at",
    },
    "control_notification_events": {"request_id"},
    "control_broadcast_deliveries": {"user_id", "telegram_id", "status"},
    "control_trigger_delivery_logs": {"user_id", "telegram_id", "dedupe_key", "result"},
    "channel_content_items": {"status", "scheduled_at", "deep_link_token"},
    "analytics_user_attribution": {
        "user_id",
        "first_source_type",
        "first_source_key",
        "first_seen_at",
        "last_source_type",
        "last_source_key",
        "last_seen_at",
    },
    "analytics_events": {
        "occurred_at",
        "user_id",
        "telegram_id",
        "event_name",
        "dedupe_key",
        "payment_record_id",
        "vpn_client_id",
        "channel_item_id",
        "tariff_code",
        "payment_method",
        "country_code",
    },
    "analytics_daily_stage_counts": {"bucket_date", "event_name", "source_type", "source_key", "events_count", "users_count"},
    "analytics_daily_stage_segments": {
        "bucket_date",
        "event_name",
        "source_type",
        "source_key",
        "user_segment",
        "events_count",
        "users_count",
    },
    "analytics_daily_revenue": {
        "bucket_date",
        "source_type",
        "source_key",
        "payment_kind",
        "payments_count",
        "revenue_amount_rub",
    },
    "analytics_daily_revenue_segments": {
        "bucket_date",
        "source_type",
        "source_key",
        "payment_kind",
        "user_segment",
        "payments_count",
        "revenue_amount_rub",
    },
    "analytics_daily_connection": {"bucket_date", "source_type", "source_key", "first_connection_success_count"},
    "analytics_daily_payment_failure_reasons": {
        "bucket_date",
        "source_type",
        "source_key",
        "payment_method",
        "reason_key",
        "failures_count",
    },
    "analytics_daily_attribution_integrity": {
        "bucket_date",
        "issue_type",
        "issue_count",
        "affected_users_count",
        "total_bot_start_count",
    },
    "analytics_cohort_retention": {"cohort_type", "cohort_date", "period_days", "cohort_size", "active_users"},
    "analytics_refresh_state": {"state_key", "cursor_at", "updated_at"},
    "analytics_hourly_ops_incidents": {
        "bucket_hour",
        "incident_class",
        "category",
        "severity",
        "event_type",
        "created_count",
        "resolved_count",
        "repeated_count",
        "unique_entities_count",
        "updated_at",
    },
    "analytics_hourly_ops_snapshots": {
        "bucket_hour",
        "repair_needed_open_count",
        "unresolved_incident_count",
        "unresolved_warning_count",
        "unresolved_critical_count",
        "unresolved_access_count",
        "unresolved_node_count",
        "unresolved_service_count",
        "provisioning_failure_events_24h",
        "reconcile_failure_events_24h",
        "updated_at",
    },
    "analytics_runtime_status": {
        "status_key",
        "status_group",
        "status_value",
        "observed_at",
        "detail_json",
        "updated_at",
    },
    "daily_news_review_items": {"id", "status", "post_text"},
    "promo_codes": {
        "code",
        "kind",
        "title",
        "description",
        "discount_percent",
        "grant_days",
        "max_redemptions",
        "redeemed_count",
        "status",
        "created_by_admin_id",
        "buyer_user_id",
        "payment_record_id",
        "expires_at",
        "created_at",
        "updated_at",
    },
    "promo_code_redemptions": {
        "promo_code_id",
        "user_id",
        "status",
        "discount_percent",
        "granted_days",
        "applied_payment_record_id",
        "note",
        "redeemed_at",
        "applied_at",
    },
}
REQUIRED_SCHEMA_INDEXES = {
    "idx_users_ref_code",
    "idx_users_is_synthetic_created_at",
    "uq_payment_records_method_external_id",
    "idx_payment_records_user_created_at",
    "idx_payment_records_user_status_created_at",
    "idx_payment_records_status_created_at",
    "idx_payment_records_method_status_created_at",
    "idx_vpn_clients_user_created_at",
    "uq_public_subscription_links_token",
    "idx_public_subscription_links_user_active",
    "uq_public_subscription_routes_user_country_slot",
    "uq_public_subscription_routes_client_uuid",
    "uq_public_subscription_routes_email",
    "idx_public_subscription_routes_user_status",
    "idx_public_subscription_routes_country_status",
    "idx_vpn_repair_events_user_result_created_at",
    "idx_finance_entries_source_type_source_id",
    "idx_support_tickets_status_updated_at",
    "idx_support_tickets_assigned_status_updated_at",
    "idx_support_ticket_messages_ticket_created_at",
    "idx_device_slot_entitlements_user_status",
    "idx_device_compensation_jobs_status_next_attempt_at",
    "idx_device_compensation_jobs_dedupe_status",
    "idx_device_compensation_jobs_request_id",
    "idx_user_deletion_jobs_status_updated_at",
    "idx_user_deletion_jobs_user_status",
    "idx_control_notification_events_request_id",
    "uq_analytics_user_attribution_user_id",
    "idx_analytics_user_attribution_first_source",
    "idx_analytics_user_attribution_last_source",
    "uq_analytics_events_dedupe_key",
    "idx_analytics_events_name_occurred_at",
    "idx_analytics_events_user_occurred_at",
    "idx_analytics_events_channel_item_occurred_at",
    "uq_analytics_daily_stage_counts_bucket",
    "idx_analytics_daily_stage_counts_bucket_event",
    "uq_analytics_daily_stage_segments_bucket",
    "idx_analytics_daily_stage_segments_bucket_event",
    "uq_analytics_daily_revenue_bucket",
    "idx_analytics_daily_revenue_bucket",
    "uq_analytics_daily_revenue_segments_bucket",
    "idx_analytics_daily_revenue_segments_bucket",
    "uq_analytics_daily_connection_bucket",
    "idx_analytics_daily_connection_bucket",
    "uq_analytics_daily_payment_failure_reasons_bucket",
    "idx_analytics_daily_payment_failure_reasons_bucket",
    "uq_analytics_daily_attribution_integrity_bucket",
    "idx_analytics_daily_attribution_integrity_bucket",
    "uq_analytics_cohort_retention_bucket",
    "idx_analytics_cohort_retention_type_date",
    "uq_analytics_hourly_ops_incidents_bucket",
    "idx_analytics_hourly_ops_incidents_bucket",
    "uq_analytics_hourly_ops_snapshots_bucket",
    "idx_analytics_hourly_ops_snapshots_bucket",
    "idx_analytics_runtime_status_group_updated_at",
    "uq_promo_codes_code",
    "uq_promo_codes_payment_record_id",
    "idx_promo_codes_status_kind_created_at",
    "idx_promo_codes_expires_at",
    "uq_promo_code_redemptions_user",
    "idx_promo_code_redemptions_user_status",
    "idx_promo_code_redemptions_promo_status",
}


CORE_SCHEMA_MIGRATIONS = (
    SchemaMigrationStep("core_001_users_subscription_started_at", "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_started_at TIMESTAMP NULL"),
    SchemaMigrationStep("core_002_users_subscription_expires_at", "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_expires_at TIMESTAMP NULL"),
    SchemaMigrationStep("core_003_users_subscription_status", "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_status VARCHAR(50) NOT NULL DEFAULT 'inactive'"),
    SchemaMigrationStep("core_004_users_subscription_source", "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_source VARCHAR(50) NULL"),
    SchemaMigrationStep("core_005_users_trial_channel_unsubscribed_at", "ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_channel_unsubscribed_at TIMESTAMP NULL"),
    SchemaMigrationStep("core_006_users_trial_activity_level", "ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_activity_level VARCHAR(20) NOT NULL DEFAULT 'low'"),
    SchemaMigrationStep("core_007_users_trial_engaged_at", "ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_engaged_at TIMESTAMP NULL"),
    SchemaMigrationStep("core_008_users_vpn_repair_needed", "ALTER TABLE users ADD COLUMN IF NOT EXISTS vpn_repair_needed BOOLEAN NOT NULL DEFAULT FALSE"),
    SchemaMigrationStep("core_009_users_vpn_repair_reason", "ALTER TABLE users ADD COLUMN IF NOT EXISTS vpn_repair_reason TEXT NULL"),
    SchemaMigrationStep("core_010_users_vpn_repair_marked_at", "ALTER TABLE users ADD COLUMN IF NOT EXISTS vpn_repair_marked_at TIMESTAMP NULL"),
    SchemaMigrationStep("core_011_users_preferred_mode", "ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_mode VARCHAR(20) NULL"),
    SchemaMigrationStep("core_012_users_preferred_protocol", "ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_protocol VARCHAR(50) NOT NULL DEFAULT 'vless'"),
    SchemaMigrationStep("core_013_users_is_blocked", "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_blocked BOOLEAN NOT NULL DEFAULT FALSE"),
    SchemaMigrationStep("core_014_users_referred_by_user_id", "ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by_user_id INTEGER NULL"),
    SchemaMigrationStep("core_015_users_ref_code", "ALTER TABLE users ADD COLUMN IF NOT EXISTS ref_code VARCHAR(32) NULL"),
    SchemaMigrationStep("core_016_users_referral_bonus_granted", "ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_bonus_granted BOOLEAN NOT NULL DEFAULT FALSE"),
    SchemaMigrationStep("core_017_users_referral_earned_total_rub", "ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_earned_total_rub INTEGER NOT NULL DEFAULT 0"),
    SchemaMigrationStep("core_018_users_balance_rub", "ALTER TABLE users ADD COLUMN IF NOT EXISTS balance_rub INTEGER NOT NULL DEFAULT 0"),
    SchemaMigrationStep("core_019_users_balance_reserved_rub", "ALTER TABLE users ADD COLUMN IF NOT EXISTS balance_reserved_rub INTEGER NOT NULL DEFAULT 0"),
    SchemaMigrationStep("core_020_users_referral_balance_migrated_at", "ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_balance_migrated_at TIMESTAMP NULL"),
    SchemaMigrationStep("core_021_users_last_activity_at", "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMP NULL"),
    SchemaMigrationStep("core_021a_users_is_synthetic", "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_synthetic BOOLEAN NOT NULL DEFAULT FALSE"),
    SchemaMigrationStep(
        "core_021b_users_is_synthetic_backfill",
        (
            "UPDATE users "
            "SET is_synthetic = TRUE "
            "WHERE COALESCE(is_synthetic, FALSE) = FALSE "
            "  AND ("
            "      LOWER(COALESCE(username, '')) LIKE 'manual_payment_%' "
            "   OR LOWER(COALESCE(username, '')) LIKE 'smoke_%' "
            "   OR LOWER(COALESCE(username, '')) LIKE 'test_%' "
            "   OR LOWER(COALESCE(username, '')) LIKE 'debug_%' "
            "   OR LOWER(COALESCE(username, '')) LIKE 'seed_%' "
            "   OR LOWER(COALESCE(username, '')) LIKE 'bridge_%'"
            "  )"
        ),
        (
            "SELECT NOT EXISTS ("
            "    SELECT 1 "
            "    FROM users "
            "    WHERE COALESCE(is_synthetic, FALSE) = FALSE "
            "      AND ("
            "          LOWER(COALESCE(username, '')) LIKE 'manual_payment_%' "
            "       OR LOWER(COALESCE(username, '')) LIKE 'smoke_%' "
            "       OR LOWER(COALESCE(username, '')) LIKE 'test_%' "
            "       OR LOWER(COALESCE(username, '')) LIKE 'debug_%' "
            "       OR LOWER(COALESCE(username, '')) LIKE 'seed_%' "
            "       OR LOWER(COALESCE(username, '')) LIKE 'bridge_%'"
            "      )"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_022_users_ref_code_unique_index",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_ref_code ON users (ref_code)",
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_users_ref_code'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_022a_users_is_synthetic_created_at_index",
        "CREATE INDEX IF NOT EXISTS idx_users_is_synthetic_created_at ON users (is_synthetic, created_at DESC)",
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_users_is_synthetic_created_at'"
            ")"
        ),
    ),
    SchemaMigrationStep("core_023_vpn_clients_xui_client_id", "ALTER TABLE vpn_clients ADD COLUMN IF NOT EXISTS xui_client_id VARCHAR(255) NULL"),
    SchemaMigrationStep("core_024_vpn_clients_client_data", "ALTER TABLE vpn_clients ADD COLUMN IF NOT EXISTS client_data TEXT NULL"),
    SchemaMigrationStep("core_025_payment_records_tariff_code", "ALTER TABLE payment_records ADD COLUMN IF NOT EXISTS tariff_code VARCHAR(50) NULL"),
    SchemaMigrationStep("core_026_payment_records_list_price_amount", "ALTER TABLE payment_records ADD COLUMN IF NOT EXISTS list_price_amount INTEGER NOT NULL DEFAULT 0"),
    SchemaMigrationStep("core_027_payment_records_balance_reserved_amount", "ALTER TABLE payment_records ADD COLUMN IF NOT EXISTS balance_reserved_amount INTEGER NOT NULL DEFAULT 0"),
    SchemaMigrationStep("core_028_payment_records_balance_applied_amount", "ALTER TABLE payment_records ADD COLUMN IF NOT EXISTS balance_applied_amount INTEGER NOT NULL DEFAULT 0"),
    SchemaMigrationStep("core_029_payment_records_reference", "ALTER TABLE payment_records ADD COLUMN IF NOT EXISTS reference VARCHAR(255) NULL"),
    SchemaMigrationStep("core_030_payment_records_metadata_json", "ALTER TABLE payment_records ADD COLUMN IF NOT EXISTS metadata_json TEXT NULL"),
    SchemaMigrationStep("core_031_payment_records_reviewed_by_actor_id", "ALTER TABLE payment_records ADD COLUMN IF NOT EXISTS reviewed_by_actor_id VARCHAR(255) NULL"),
    SchemaMigrationStep("core_032_payment_records_reviewed_by_actor_name", "ALTER TABLE payment_records ADD COLUMN IF NOT EXISTS reviewed_by_actor_name VARCHAR(255) NULL"),
    SchemaMigrationStep("core_033_payment_records_reviewed_at", "ALTER TABLE payment_records ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP NULL"),
    SchemaMigrationStep("core_034_payment_records_rejection_reason", "ALTER TABLE payment_records ADD COLUMN IF NOT EXISTS rejection_reason TEXT NULL"),
    SchemaMigrationStep("core_035_payment_records_expires_at", "ALTER TABLE payment_records ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP NULL"),
    SchemaMigrationStep("core_036_payment_records_confirmed_at", "ALTER TABLE payment_records ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMP NULL"),
    SchemaMigrationStep(
        "core_037_payment_records_method_external_id_unique_index",
        (
            "DO $$ "
            "BEGIN "
            "    IF NOT EXISTS ("
            "        SELECT 1 "
            "        FROM pg_indexes "
            "        WHERE schemaname = current_schema() "
            "          AND indexname = 'uq_payment_records_method_external_id'"
            "    ) THEN "
            "        IF NOT EXISTS ("
            "            SELECT 1 "
            "            FROM payment_records "
            "            WHERE external_payment_id IS NOT NULL "
            "            GROUP BY payment_method, external_payment_id "
            "            HAVING COUNT(*) > 1"
            "        ) THEN "
            "            EXECUTE "
            "                'CREATE UNIQUE INDEX uq_payment_records_method_external_id "
            "                 ON payment_records (payment_method, external_payment_id) "
            "                 WHERE external_payment_id IS NOT NULL'; "
            "        END IF; "
            "    END IF; "
            "END $$"
        ),
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'uq_payment_records_method_external_id'"
            ")"
        ),
    ),
    SchemaMigrationStep("core_038_support_ticket_messages_attachment_file_id", "ALTER TABLE support_ticket_messages ADD COLUMN IF NOT EXISTS attachment_file_id VARCHAR(255) NULL"),
    SchemaMigrationStep("core_039_support_ticket_messages_attachment_file_unique_id", "ALTER TABLE support_ticket_messages ADD COLUMN IF NOT EXISTS attachment_file_unique_id VARCHAR(255) NULL"),
    SchemaMigrationStep("core_040_support_ticket_messages_attachment_kind", "ALTER TABLE support_ticket_messages ADD COLUMN IF NOT EXISTS attachment_kind VARCHAR(50) NULL"),
    SchemaMigrationStep("core_041_support_ticket_messages_attachment_name", "ALTER TABLE support_ticket_messages ADD COLUMN IF NOT EXISTS attachment_name VARCHAR(255) NULL"),
    SchemaMigrationStep("core_042_support_ticket_messages_attachment_mime_type", "ALTER TABLE support_ticket_messages ADD COLUMN IF NOT EXISTS attachment_mime_type VARCHAR(255) NULL"),
    SchemaMigrationStep("core_043_support_ticket_messages_attachment_size", "ALTER TABLE support_ticket_messages ADD COLUMN IF NOT EXISTS attachment_size INTEGER NULL"),
    SchemaMigrationStep("core_044_finance_entries_counterparty_admin_id", "ALTER TABLE finance_entries ADD COLUMN IF NOT EXISTS counterparty_admin_id INTEGER NULL"),
    SchemaMigrationStep("core_045_finance_entries_status", "ALTER TABLE finance_entries ADD COLUMN IF NOT EXISTS status VARCHAR(50) NOT NULL DEFAULT 'draft'"),
    SchemaMigrationStep("core_046_finance_entries_source_type", "ALTER TABLE finance_entries ADD COLUMN IF NOT EXISTS source_type VARCHAR(100) NULL"),
    SchemaMigrationStep("core_047_finance_entries_source_id", "ALTER TABLE finance_entries ADD COLUMN IF NOT EXISTS source_id VARCHAR(255) NULL"),
    SchemaMigrationStep("core_048_finance_entries_approved_by_admin_id", "ALTER TABLE finance_entries ADD COLUMN IF NOT EXISTS approved_by_admin_id INTEGER NULL"),
    SchemaMigrationStep("core_049_finance_entries_approved_at", "ALTER TABLE finance_entries ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP NULL"),
    SchemaMigrationStep("core_050_finance_entries_period_key", "ALTER TABLE finance_entries ADD COLUMN IF NOT EXISTS period_key VARCHAR(20) NULL"),
    SchemaMigrationStep(
        "core_051_device_slot_entitlements_user_status_index",
        "CREATE INDEX IF NOT EXISTS idx_device_slot_entitlements_user_status ON device_slot_entitlements (user_id, status)",
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_device_slot_entitlements_user_status'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_052_payment_records_user_created_at_index",
        "CREATE INDEX IF NOT EXISTS idx_payment_records_user_created_at ON payment_records (user_id, created_at DESC)",
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_payment_records_user_created_at'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_053_payment_records_status_created_at_index",
        "CREATE INDEX IF NOT EXISTS idx_payment_records_status_created_at ON payment_records (payment_status, created_at DESC)",
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_payment_records_status_created_at'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_054_payment_records_method_status_created_at_index",
        "CREATE INDEX IF NOT EXISTS idx_payment_records_method_status_created_at ON payment_records (payment_method, payment_status, created_at DESC)",
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_payment_records_method_status_created_at'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_055_finance_entries_source_type_source_id_index",
        "CREATE INDEX IF NOT EXISTS idx_finance_entries_source_type_source_id ON finance_entries (source_type, source_id)",
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_finance_entries_source_type_source_id'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_056_support_tickets_status_updated_at_index",
        "CREATE INDEX IF NOT EXISTS idx_support_tickets_status_updated_at ON support_tickets (status, updated_at DESC)",
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_support_tickets_status_updated_at'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_057_support_ticket_messages_ticket_created_at_index",
        "CREATE INDEX IF NOT EXISTS idx_support_ticket_messages_ticket_created_at ON support_ticket_messages (ticket_id, created_at DESC)",
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_support_ticket_messages_ticket_created_at'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_058_control_notification_events_request_id",
        "ALTER TABLE control_notification_events ADD COLUMN IF NOT EXISTS request_id VARCHAR(64) NULL",
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM information_schema.columns "
            "    WHERE table_schema = current_schema() "
            "      AND table_name = 'control_notification_events' "
            "      AND column_name = 'request_id'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_059_control_notification_events_request_id_index",
        "CREATE INDEX IF NOT EXISTS idx_control_notification_events_request_id ON control_notification_events (request_id)",
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_control_notification_events_request_id'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_060_vpn_clients_user_created_at_index",
        "CREATE INDEX IF NOT EXISTS idx_vpn_clients_user_created_at ON vpn_clients (user_id, created_at DESC)",
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_vpn_clients_user_created_at'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_061_payment_records_user_status_created_at_index",
        "CREATE INDEX IF NOT EXISTS idx_payment_records_user_status_created_at ON payment_records (user_id, payment_status, created_at DESC)",
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_payment_records_user_status_created_at'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_062_support_tickets_assigned_status_updated_at_index",
        "CREATE INDEX IF NOT EXISTS idx_support_tickets_assigned_status_updated_at ON support_tickets (assigned_admin_id, status, updated_at DESC)",
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_support_tickets_assigned_status_updated_at'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_063_vpn_repair_events_user_result_created_at_index",
        "CREATE INDEX IF NOT EXISTS idx_vpn_repair_events_user_result_created_at ON vpn_repair_events (user_id, result, created_at DESC)",
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_vpn_repair_events_user_result_created_at'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_064_user_deletion_jobs_table",
        (
            "CREATE TABLE IF NOT EXISTS user_deletion_jobs ("
            "id SERIAL PRIMARY KEY, "
            "user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL, "
            "telegram_id BIGINT NULL, "
            "admin_id INTEGER NULL, "
            "status VARCHAR(32) NOT NULL DEFAULT 'running', "
            "stage VARCHAR(64) NOT NULL DEFAULT 'created', "
            "ip_address VARCHAR(64) NULL, "
            "payload_json TEXT NOT NULL DEFAULT '{}', "
            "last_error TEXT NULL, "
            "completed_at TIMESTAMP NULL, "
            "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ")"
        ),
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM information_schema.tables "
            "    WHERE table_schema = current_schema() "
            "      AND table_name = 'user_deletion_jobs'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_065_user_deletion_jobs_status_updated_at_index",
        "CREATE INDEX IF NOT EXISTS idx_user_deletion_jobs_status_updated_at ON user_deletion_jobs (status, updated_at DESC)",
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_user_deletion_jobs_status_updated_at'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_066_user_deletion_jobs_user_status_index",
        "CREATE INDEX IF NOT EXISTS idx_user_deletion_jobs_user_status ON user_deletion_jobs (user_id, status)",
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_user_deletion_jobs_user_status'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_067_device_compensation_jobs_request_id",
        "ALTER TABLE device_compensation_jobs ADD COLUMN IF NOT EXISTS request_id VARCHAR(64) NULL",
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM information_schema.columns "
            "    WHERE table_schema = current_schema() "
            "      AND table_name = 'device_compensation_jobs' "
            "      AND column_name = 'request_id'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_068_device_compensation_jobs_request_id_index",
        "CREATE INDEX IF NOT EXISTS idx_device_compensation_jobs_request_id ON device_compensation_jobs (request_id)",
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_device_compensation_jobs_request_id'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_069_analytics_cohort_retention_active_users",
        "ALTER TABLE analytics_cohort_retention ADD COLUMN IF NOT EXISTS active_users INTEGER NOT NULL DEFAULT 0",
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM information_schema.columns "
            "    WHERE table_schema = current_schema() "
            "      AND table_name = 'analytics_cohort_retention' "
            "      AND column_name = 'active_users'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_070_analytics_daily_stage_segments_table",
        (
            "CREATE TABLE IF NOT EXISTS analytics_daily_stage_segments ("
            "id SERIAL PRIMARY KEY, "
            "bucket_date DATE NOT NULL, "
            "event_name VARCHAR(80) NOT NULL, "
            "source_mode VARCHAR(20) NOT NULL DEFAULT 'first', "
            "source_type VARCHAR(50) NOT NULL DEFAULT 'organic_bot', "
            "source_key VARCHAR(255) NOT NULL DEFAULT 'organic_bot', "
            "channel_item_id INTEGER NULL REFERENCES channel_content_items(id) ON DELETE SET NULL, "
            "content_type VARCHAR(30) NULL, "
            "user_segment VARCHAR(20) NOT NULL DEFAULT 'returning', "
            "events_count INTEGER NOT NULL DEFAULT 0, "
            "users_count INTEGER NOT NULL DEFAULT 0, "
            "updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ")"
        ),
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM information_schema.tables "
            "    WHERE table_schema = current_schema() "
            "      AND table_name = 'analytics_daily_stage_segments'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_071_analytics_daily_stage_segments_unique_index",
        (
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_analytics_daily_stage_segments_bucket "
            "ON analytics_daily_stage_segments (bucket_date, event_name, source_mode, source_type, source_key, channel_item_id, user_segment)"
        ),
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'uq_analytics_daily_stage_segments_bucket'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_072_analytics_daily_stage_segments_bucket_index",
        (
            "CREATE INDEX IF NOT EXISTS idx_analytics_daily_stage_segments_bucket_event "
            "ON analytics_daily_stage_segments (bucket_date, event_name, user_segment)"
        ),
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_analytics_daily_stage_segments_bucket_event'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_073_analytics_daily_revenue_segments_table",
        (
            "CREATE TABLE IF NOT EXISTS analytics_daily_revenue_segments ("
            "id SERIAL PRIMARY KEY, "
            "bucket_date DATE NOT NULL, "
            "source_mode VARCHAR(20) NOT NULL DEFAULT 'first', "
            "source_type VARCHAR(50) NOT NULL DEFAULT 'organic_bot', "
            "source_key VARCHAR(255) NOT NULL DEFAULT 'organic_bot', "
            "channel_item_id INTEGER NULL REFERENCES channel_content_items(id) ON DELETE SET NULL, "
            "content_type VARCHAR(30) NULL, "
            "tariff_code VARCHAR(50) NULL, "
            "payment_method VARCHAR(50) NULL, "
            "payment_kind VARCHAR(20) NOT NULL DEFAULT 'unknown', "
            "user_segment VARCHAR(20) NOT NULL DEFAULT 'returning', "
            "payments_count INTEGER NOT NULL DEFAULT 0, "
            "revenue_amount_rub INTEGER NOT NULL DEFAULT 0, "
            "updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ")"
        ),
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM information_schema.tables "
            "    WHERE table_schema = current_schema() "
            "      AND table_name = 'analytics_daily_revenue_segments'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_074_analytics_daily_revenue_segments_unique_index",
        (
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_analytics_daily_revenue_segments_bucket "
            "ON analytics_daily_revenue_segments (bucket_date, source_mode, source_type, source_key, channel_item_id, tariff_code, payment_method, payment_kind, user_segment)"
        ),
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'uq_analytics_daily_revenue_segments_bucket'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_075_analytics_daily_revenue_segments_bucket_index",
        (
            "CREATE INDEX IF NOT EXISTS idx_analytics_daily_revenue_segments_bucket "
            "ON analytics_daily_revenue_segments (bucket_date, payment_method, user_segment)"
        ),
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_analytics_daily_revenue_segments_bucket'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_076_analytics_daily_payment_failure_reasons_table",
        (
            "CREATE TABLE IF NOT EXISTS analytics_daily_payment_failure_reasons ("
            "id SERIAL PRIMARY KEY, "
            "bucket_date DATE NOT NULL, "
            "source_mode VARCHAR(20) NOT NULL DEFAULT 'first', "
            "source_type VARCHAR(50) NOT NULL DEFAULT 'organic_bot', "
            "source_key VARCHAR(255) NOT NULL DEFAULT 'organic_bot', "
            "channel_item_id INTEGER NULL REFERENCES channel_content_items(id) ON DELETE SET NULL, "
            "content_type VARCHAR(30) NULL, "
            "payment_method VARCHAR(50) NULL, "
            "reason_key VARCHAR(80) NOT NULL, "
            "failures_count INTEGER NOT NULL DEFAULT 0, "
            "updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ")"
        ),
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM information_schema.tables "
            "    WHERE table_schema = current_schema() "
            "      AND table_name = 'analytics_daily_payment_failure_reasons'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_077_analytics_daily_payment_failure_reasons_unique_index",
        (
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_analytics_daily_payment_failure_reasons_bucket "
            "ON analytics_daily_payment_failure_reasons (bucket_date, source_mode, source_type, source_key, channel_item_id, payment_method, reason_key)"
        ),
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'uq_analytics_daily_payment_failure_reasons_bucket'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_078_analytics_daily_payment_failure_reasons_bucket_index",
        (
            "CREATE INDEX IF NOT EXISTS idx_analytics_daily_payment_failure_reasons_bucket "
            "ON analytics_daily_payment_failure_reasons (bucket_date, payment_method, reason_key)"
        ),
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_analytics_daily_payment_failure_reasons_bucket'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_079_analytics_daily_attribution_integrity_table",
        (
            "CREATE TABLE IF NOT EXISTS analytics_daily_attribution_integrity ("
            "id SERIAL PRIMARY KEY, "
            "bucket_date DATE NOT NULL, "
            "issue_type VARCHAR(80) NOT NULL, "
            "issue_count INTEGER NOT NULL DEFAULT 0, "
            "affected_users_count INTEGER NOT NULL DEFAULT 0, "
            "total_bot_start_count INTEGER NOT NULL DEFAULT 0, "
            "updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ")"
        ),
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM information_schema.tables "
            "    WHERE table_schema = current_schema() "
            "      AND table_name = 'analytics_daily_attribution_integrity'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_080_analytics_daily_attribution_integrity_unique_index",
        (
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_analytics_daily_attribution_integrity_bucket "
            "ON analytics_daily_attribution_integrity (bucket_date, issue_type)"
        ),
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'uq_analytics_daily_attribution_integrity_bucket'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_081_analytics_daily_attribution_integrity_bucket_index",
        (
            "CREATE INDEX IF NOT EXISTS idx_analytics_daily_attribution_integrity_bucket "
            "ON analytics_daily_attribution_integrity (bucket_date, issue_type)"
        ),
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_analytics_daily_attribution_integrity_bucket'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_082_analytics_daily_revenue_payment_kind_column",
        "ALTER TABLE analytics_daily_revenue ADD COLUMN IF NOT EXISTS payment_kind VARCHAR(20) NOT NULL DEFAULT 'unknown'",
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM information_schema.columns "
            "    WHERE table_schema = current_schema() "
            "      AND table_name = 'analytics_daily_revenue' "
            "      AND column_name = 'payment_kind'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_083_analytics_daily_revenue_unique_index_recreate_drop",
        (
            "DO $$ "
            "BEGIN "
            "  IF EXISTS ("
            "    SELECT 1 "
            "    FROM pg_constraint "
            "    WHERE conname = 'uq_analytics_daily_revenue_bucket' "
            "      AND conrelid = 'analytics_daily_revenue'::regclass"
            "  ) THEN "
            "    EXECUTE 'ALTER TABLE analytics_daily_revenue DROP CONSTRAINT uq_analytics_daily_revenue_bucket'; "
            "  ELSIF EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'uq_analytics_daily_revenue_bucket'"
            "  ) THEN "
            "    EXECUTE 'DROP INDEX uq_analytics_daily_revenue_bucket'; "
            "  END IF; "
            "END $$"
        ),
        "SELECT TRUE",
    ),
    SchemaMigrationStep(
        "core_084_analytics_daily_revenue_unique_index_recreate",
        (
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_analytics_daily_revenue_bucket "
            "ON analytics_daily_revenue (bucket_date, source_mode, source_type, source_key, channel_item_id, tariff_code, payment_method, payment_kind)"
        ),
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'uq_analytics_daily_revenue_bucket'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_085_analytics_daily_revenue_segments_payment_kind_column",
        "ALTER TABLE analytics_daily_revenue_segments ADD COLUMN IF NOT EXISTS payment_kind VARCHAR(20) NOT NULL DEFAULT 'unknown'",
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM information_schema.columns "
            "    WHERE table_schema = current_schema() "
            "      AND table_name = 'analytics_daily_revenue_segments' "
            "      AND column_name = 'payment_kind'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_086_analytics_daily_revenue_segments_unique_index_recreate_drop",
        (
            "DO $$ "
            "BEGIN "
            "  IF EXISTS ("
            "    SELECT 1 "
            "    FROM pg_constraint "
            "    WHERE conname = 'uq_analytics_daily_revenue_segments_bucket' "
            "      AND conrelid = 'analytics_daily_revenue_segments'::regclass"
            "  ) THEN "
            "    EXECUTE 'ALTER TABLE analytics_daily_revenue_segments DROP CONSTRAINT uq_analytics_daily_revenue_segments_bucket'; "
            "  ELSIF EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'uq_analytics_daily_revenue_segments_bucket'"
            "  ) THEN "
            "    EXECUTE 'DROP INDEX uq_analytics_daily_revenue_segments_bucket'; "
            "  END IF; "
            "END $$"
        ),
        "SELECT TRUE",
    ),
    SchemaMigrationStep(
        "core_087_analytics_daily_revenue_segments_unique_index_recreate",
        (
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_analytics_daily_revenue_segments_bucket "
            "ON analytics_daily_revenue_segments (bucket_date, source_mode, source_type, source_key, channel_item_id, tariff_code, payment_method, payment_kind, user_segment)"
        ),
        (
            "SELECT EXISTS ("
            "    SELECT 1 "
            "    FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'uq_analytics_daily_revenue_segments_bucket'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_088_promo_codes_table",
        (
            "CREATE TABLE IF NOT EXISTS promo_codes ("
            "id SERIAL PRIMARY KEY, "
            "code VARCHAR(64) NOT NULL, "
            "kind VARCHAR(32) NOT NULL DEFAULT 'discount_percent', "
            "title VARCHAR(255) NULL, "
            "description TEXT NULL, "
            "discount_percent INTEGER NULL, "
            "grant_days INTEGER NOT NULL DEFAULT 0, "
            "max_redemptions INTEGER NOT NULL DEFAULT 1, "
            "redeemed_count INTEGER NOT NULL DEFAULT 0, "
            "status VARCHAR(32) NOT NULL DEFAULT 'active', "
            "created_by_admin_id INTEGER NULL REFERENCES dashboard_admins(id) ON DELETE SET NULL, "
            "buyer_user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL, "
            "payment_record_id INTEGER NULL REFERENCES payment_records(id) ON DELETE SET NULL, "
            "expires_at TIMESTAMP NULL, "
            "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ")"
        ),
        (
            "SELECT EXISTS ("
            "    SELECT 1 FROM information_schema.tables "
            "    WHERE table_schema = current_schema() "
            "      AND table_name = 'promo_codes'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_089_promo_codes_code_unique_index",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_promo_codes_code ON promo_codes (code)",
        (
            "SELECT EXISTS ("
            "    SELECT 1 FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'uq_promo_codes_code'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_090_promo_codes_payment_record_unique_index",
        (
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_promo_codes_payment_record_id "
            "ON promo_codes (payment_record_id) WHERE payment_record_id IS NOT NULL"
        ),
        (
            "SELECT EXISTS ("
            "    SELECT 1 FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'uq_promo_codes_payment_record_id'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_091_promo_codes_status_kind_index",
        "CREATE INDEX IF NOT EXISTS idx_promo_codes_status_kind_created_at ON promo_codes (status, kind, created_at DESC)",
        (
            "SELECT EXISTS ("
            "    SELECT 1 FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_promo_codes_status_kind_created_at'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_092_promo_codes_expires_at_index",
        "CREATE INDEX IF NOT EXISTS idx_promo_codes_expires_at ON promo_codes (expires_at)",
        (
            "SELECT EXISTS ("
            "    SELECT 1 FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_promo_codes_expires_at'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_093_promo_code_redemptions_table",
        (
            "CREATE TABLE IF NOT EXISTS promo_code_redemptions ("
            "id SERIAL PRIMARY KEY, "
            "promo_code_id INTEGER NOT NULL REFERENCES promo_codes(id) ON DELETE CASCADE, "
            "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
            "status VARCHAR(32) NOT NULL DEFAULT 'applied', "
            "discount_percent INTEGER NULL, "
            "granted_days INTEGER NOT NULL DEFAULT 0, "
            "applied_payment_record_id INTEGER NULL REFERENCES payment_records(id) ON DELETE SET NULL, "
            "note TEXT NULL, "
            "redeemed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "applied_at TIMESTAMP NULL"
            ")"
        ),
        (
            "SELECT EXISTS ("
            "    SELECT 1 FROM information_schema.tables "
            "    WHERE table_schema = current_schema() "
            "      AND table_name = 'promo_code_redemptions'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_094_promo_code_redemptions_user_unique_index",
        (
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_promo_code_redemptions_user "
            "ON promo_code_redemptions (promo_code_id, user_id)"
        ),
        (
            "SELECT EXISTS ("
            "    SELECT 1 FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'uq_promo_code_redemptions_user'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_095_promo_code_redemptions_user_status_index",
        "CREATE INDEX IF NOT EXISTS idx_promo_code_redemptions_user_status ON promo_code_redemptions (user_id, status)",
        (
            "SELECT EXISTS ("
            "    SELECT 1 FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_promo_code_redemptions_user_status'"
            ")"
        ),
    ),
    SchemaMigrationStep(
        "core_096_promo_code_redemptions_promo_status_index",
        "CREATE INDEX IF NOT EXISTS idx_promo_code_redemptions_promo_status ON promo_code_redemptions (promo_code_id, status)",
        (
            "SELECT EXISTS ("
            "    SELECT 1 FROM pg_indexes "
            "    WHERE schemaname = current_schema() "
            "      AND indexname = 'idx_promo_code_redemptions_promo_status'"
            ")"
        ),
    ),
)

SCHEMA_UPDATES = [step.statement for step in CORE_SCHEMA_MIGRATIONS]


async def ensure_schema() -> None:
    global _schema_ready

    if _schema_ready:
        return

    if os.getenv("AUTO_APPLY_SCHEMA", "0") != "1":
        missing = await _detect_missing_required_schema()
        if missing:
            joined = ", ".join(missing[:8])
            if len(missing) > 8:
                joined += ", ..."
            raise RuntimeError(
                "Database schema is not ready for the current code. "
                f"Missing required objects: {joined}. "
                "Enable AUTO_APPLY_SCHEMA=1 for controlled schema updates or apply the schema migration first."
            )
        _schema_ready = True
        return

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await apply_schema_migrations(connection, CORE_SCHEMA_MIGRATIONS)
        missing = await _detect_missing_required_schema(connection=connection)
        if missing:
            joined = ", ".join(missing[:8])
            if len(missing) > 8:
                joined += ", ..."
            raise RuntimeError(
                "Database schema auto-apply did not bring the schema to the required state. "
                f"Missing required objects after migration: {joined}."
            )

    _schema_ready = True


async def apply_schema_migrations(connection, migrations: Iterable[SchemaMigrationStep]) -> None:
    await _ensure_schema_migration_registry(connection)
    applied_steps = await _load_applied_schema_migration_keys(connection)

    for migration in migrations:
        if migration.key in applied_steps:
            continue
        await connection.execute(text(migration.statement))
        if not await _migration_effect_present(connection, migration):
            continue
        await _record_applied_schema_migration(connection, migration.key)
        applied_steps.add(migration.key)


async def _ensure_schema_migration_registry(connection) -> None:
    await connection.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {SCHEMA_MIGRATION_REGISTRY_TABLE} ("
            "step_key VARCHAR(255) PRIMARY KEY, "
            "applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ")"
        )
    )


async def _load_applied_schema_migration_keys(connection) -> set[str]:
    rows = await connection.execute(
        text(f"SELECT step_key FROM {SCHEMA_MIGRATION_REGISTRY_TABLE}")
    )
    return {str(item) for item in rows.scalars().all()}


async def _record_applied_schema_migration(connection, step_key: str) -> None:
    await connection.execute(
        text(
            f"INSERT INTO {SCHEMA_MIGRATION_REGISTRY_TABLE} (step_key) "
            "VALUES (:step_key) "
            "ON CONFLICT (step_key) DO NOTHING"
        ),
        {"step_key": step_key},
    )


async def _migration_effect_present(connection, migration: SchemaMigrationStep) -> bool:
    if not migration.verify_query:
        return True
    result = await connection.execute(text(migration.verify_query))
    return bool(result.scalar())


async def _detect_missing_required_schema(connection=None) -> list[str]:
    if connection is None:
        async with engine.begin() as owned_connection:
            return await _detect_missing_required_schema(connection=owned_connection)

    table_rows = await connection.execute(
        text(
            "SELECT table_name "
            "FROM information_schema.tables "
            "WHERE table_schema = current_schema()"
        )
    )
    existing_tables = {str(item) for item in table_rows.scalars().all()}
    missing: list[str] = []

    for table_name, required_columns in REQUIRED_SCHEMA_COLUMNS.items():
        if table_name not in existing_tables:
            missing.append(table_name)
            continue
        column_rows = await connection.execute(
            text(
                "SELECT column_name "
                "FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "AND table_name = :table_name"
            ),
            {"table_name": table_name},
        )
        existing_columns = {str(item) for item in column_rows.scalars().all()}
        for column_name in sorted(required_columns):
            if column_name not in existing_columns:
                missing.append(f"{table_name}.{column_name}")

    index_rows = await connection.execute(
        text(
            "SELECT indexname "
            "FROM pg_indexes "
            "WHERE schemaname = current_schema()"
        )
    )
    existing_indexes = {str(item) for item in index_rows.scalars().all()}
    for index_name in sorted(REQUIRED_SCHEMA_INDEXES):
        if index_name not in existing_indexes:
            missing.append(f"index:{index_name}")

    return missing
