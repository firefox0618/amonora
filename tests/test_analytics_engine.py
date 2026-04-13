import os
import tempfile
import unittest

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "1")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASS", "test")
os.environ.setdefault("XUI_URL", "http://127.0.0.1:12053")
os.environ.setdefault("XUI_USERNAME", "test")
os.environ.setdefault("XUI_PASSWORD", "test")
os.environ.setdefault("CHANNEL_ID", "1")

import backend.core.analytics as analytics
from backend.core.database import Base
from backend.core.models import (
    AnalyticsDailyConnection,
    AnalyticsDailyAttributionIntegrity,
    AnalyticsDailyPaymentFailureReason,
    AnalyticsDailyRevenue,
    AnalyticsDailyRevenueSegment,
    AnalyticsDailyStageCount,
    AnalyticsDailyStageSegment,
    AnalyticsEvent,
    AnalyticsHourlyOpsIncident,
    AnalyticsHourlyOpsSnapshot,
    AnalyticsCohortRetention,
    AnalyticsRuntimeStatus,
    AnalyticsUserAttribution,
    ChannelContentItem,
    ChannelPostTouch,
    ControlNotificationEvent,
    User,
    VpnClient,
    VpnClientActivation,
)
from dashboard.models import PaymentRecord


class _AsyncSessionAdapter:
    def __init__(self, session) -> None:
        self._session = session

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._session.close()

    def add(self, value) -> None:
        self._session.add(value)

    def add_all(self, values) -> None:
        self._session.add_all(values)

    async def commit(self) -> None:
        self._session.commit()

    async def rollback(self) -> None:
        self._session.rollback()

    async def refresh(self, value) -> None:
        self._session.refresh(value)

    async def execute(self, statement):
        return self._session.execute(statement)

    async def delete(self, value) -> None:
        self._session.delete(value)


class _AsyncSessionFactory:
    def __init__(self, sessionmaker_obj) -> None:
        self._sessionmaker = sessionmaker_obj

    def __call__(self):
        return _AsyncSessionAdapter(self._sessionmaker())


class AnalyticsEngineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "analytics.sqlite3")
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        self.sync_session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        self.session_factory = _AsyncSessionFactory(self.sync_session_factory)

        self.session_patcher = patch.object(analytics, "async_session", self.session_factory)
        self.ensure_patcher = patch.object(analytics, "ensure_schema", new=AsyncMock(return_value=None))
        self.session_patcher.start()
        self.ensure_patcher.start()

    async def asyncTearDown(self) -> None:
        self.session_patcher.stop()
        self.ensure_patcher.stop()
        self.engine.dispose()
        self.temp_dir.cleanup()

    async def test_attribution_preserves_first_source_and_updates_last_source(self) -> None:
        async with self.session_factory() as session:
            session.add_all(
                [
                    User(
                        telegram_id=101,
                        username="real_user",
                        preferred_protocol="vless",
                        subscription_status="inactive",
                        trial_activity_level="low",
                    ),
                    ChannelContentItem(
                        id=77,
                        content_type="daily_news",
                        topic_brief="Attribution test",
                        status="published",
                        scheduled_at=datetime(2026, 4, 4, 7, 30, 0),
                        published_at=datetime(2026, 4, 4, 7, 45, 0),
                        deep_link_token="post-attribution-test",
                    ),
                ]
            )
            await session.commit()
            user = (await session.execute(select(User).where(User.telegram_id == 101))).scalar_one()

        first_seen = datetime(2026, 4, 4, 8, 0, 0)
        last_seen = first_seen + timedelta(hours=2)

        await analytics.upsert_user_attribution(
            user_id=user.id,
            telegram_id=user.telegram_id,
            source_type=analytics.SOURCE_TYPE_ORGANIC,
            source_key=analytics.SOURCE_TYPE_ORGANIC,
            seen_at=first_seen,
        )
        await analytics.upsert_user_attribution(
            user_id=user.id,
            telegram_id=user.telegram_id,
            source_type=analytics.SOURCE_TYPE_CHANNEL_POST,
            source_key="post_token_42",
            channel_item_id=77,
            seen_at=last_seen,
        )

        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(AnalyticsUserAttribution).where(AnalyticsUserAttribution.user_id == user.id)
                )
            ).scalar_one()

        self.assertEqual(row.first_source_type, analytics.SOURCE_TYPE_ORGANIC)
        self.assertEqual(row.first_source_key, analytics.SOURCE_TYPE_ORGANIC)
        self.assertEqual(row.last_source_type, analytics.SOURCE_TYPE_CHANNEL_POST)
        self.assertEqual(row.last_source_key, "post_token_42")
        self.assertEqual(row.last_channel_item_id, 77)
        self.assertEqual(row.first_seen_at, first_seen)
        self.assertEqual(row.last_seen_at, last_seen)

    async def test_emit_analytics_event_dedupes_skips_synthetic_users_and_triggers_refresh_once(self) -> None:
        async with self.session_factory() as session:
            session.add_all(
                [
                    User(
                        telegram_id=202,
                        username="real_user",
                        preferred_protocol="vless",
                        subscription_status="inactive",
                        trial_activity_level="low",
                    ),
                    User(
                        telegram_id=203,
                        username="bridge_shadow",
                        preferred_protocol="vless",
                        subscription_status="inactive",
                        trial_activity_level="low",
                    ),
                ]
            )
            await session.commit()
            real_user = (await session.execute(select(User).where(User.telegram_id == 202))).scalar_one()
            synthetic_user = (await session.execute(select(User).where(User.telegram_id == 203))).scalar_one()

        with patch.object(analytics, "_request_near_realtime_refresh_for_event") as refresh_mock:
            first = await analytics.emit_analytics_event(
                event_name=analytics.EVENT_BOT_START,
                user_id=real_user.id,
                telegram_id=real_user.telegram_id,
                dedupe_key="event:dedupe:1",
                payload={"source_type": analytics.SOURCE_TYPE_ORGANIC},
            )
            second = await analytics.emit_analytics_event(
                event_name=analytics.EVENT_BOT_START,
                user_id=real_user.id,
                telegram_id=real_user.telegram_id,
                dedupe_key="event:dedupe:1",
                payload={"source_type": analytics.SOURCE_TYPE_ORGANIC},
            )
            skipped = await analytics.emit_analytics_event(
                event_name=analytics.EVENT_BOT_START,
                user_id=synthetic_user.id,
                telegram_id=synthetic_user.telegram_id,
                dedupe_key="event:dedupe:synthetic",
            )

        async with self.session_factory() as session:
            rows = list((await session.execute(select(AnalyticsEvent))).scalars().all())

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(first.id, second.id)
        self.assertIsNone(skipped)
        self.assertEqual(len(rows), 1)
        refresh_mock.assert_called_once_with(analytics.EVENT_BOT_START)

    def test_realtime_refresh_trigger_is_debounced(self) -> None:
        runner_path = Path(self.temp_dir.name) / "fake-python"
        runner_path.write_text("#!/bin/sh\n", encoding="utf-8")
        trigger_path = Path(self.temp_dir.name) / "analytics-refresh-trigger.txt"

        with (
            patch.object(analytics, "ANALYTICS_REALTIME_REFRESH_RUNNER", runner_path),
            patch.object(analytics, "ANALYTICS_REALTIME_REFRESH_TRIGGER_PATH", trigger_path),
            patch.object(analytics, "ANALYTICS_REALTIME_REFRESH_MIN_INTERVAL", timedelta(seconds=60)),
            patch("backend.core.analytics.subprocess.Popen") as popen_mock,
        ):
            analytics._request_near_realtime_refresh_for_event(analytics.EVENT_BOT_START)
            analytics._request_near_realtime_refresh_for_event(analytics.EVENT_BOT_START)
            analytics._request_near_realtime_refresh_for_event(analytics.EVENT_USER_FIRST_SEEN)

        self.assertEqual(popen_mock.call_count, 1)

    async def test_emit_link_touched_event_rolls_up_source_key_without_channel_item(self) -> None:
        base_time = datetime(2026, 4, 6, 12, 0, 0)
        async with self.session_factory() as session:
            user = User(
                telegram_id=204,
                username="campaign_fallback_user",
                preferred_protocol="vless",
                subscription_status="inactive",
                trial_activity_level="low",
                created_at=base_time,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        await analytics.emit_analytics_event(
            event_name=analytics.EVENT_LINK_TOUCHED,
            user_id=user.id,
            telegram_id=user.telegram_id,
            dedupe_key="fallback:link-touched:205",
            occurred_at=base_time + timedelta(hours=1),
            payload={
                "source_type": analytics.SOURCE_TYPE_CHANNEL_POST,
                "source_key": "inst_reels_april_01",
                "channel_item_id": None,
            },
        )
        refresh_result = await analytics.refresh_analytics_rollups(force_full=True)

        async with self.session_factory() as session:
            stage_rows = list((await session.execute(select(AnalyticsDailyStageCount))).scalars().all())

        self.assertGreaterEqual(refresh_result["dates_refreshed"], 1)
        self.assertTrue(
            any(
                row.event_name == analytics.EVENT_LINK_TOUCHED
                and row.source_type == analytics.SOURCE_TYPE_CHANNEL_POST
                and row.source_key == "inst_reels_april_01"
                and row.channel_item_id is None
                for row in stage_rows
            )
        )

    async def test_backfill_attribution_preserves_old_organic_first_and_updates_last_from_fallback_token(self) -> None:
        base_time = datetime(2026, 4, 6, 8, 0, 0)
        async with self.session_factory() as session:
            user = User(
                telegram_id=205,
                username="existing_user",
                preferred_protocol="vless",
                subscription_status="inactive",
                trial_activity_level="low",
                created_at=base_time,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        await analytics.upsert_user_attribution(
            user_id=user.id,
            telegram_id=user.telegram_id,
            source_type=analytics.SOURCE_TYPE_ORGANIC,
            source_key=analytics.SOURCE_TYPE_ORGANIC,
            seen_at=base_time,
        )
        await analytics.emit_analytics_event(
            event_name=analytics.EVENT_LINK_TOUCHED,
            user_id=user.id,
            telegram_id=user.telegram_id,
            dedupe_key="fallback:link-touched:205",
            occurred_at=base_time + timedelta(hours=1),
            payload={
                "source_type": analytics.SOURCE_TYPE_CHANNEL_POST,
                "source_key": "inst_reels_april_01",
                "channel_item_id": None,
            },
        )
        await analytics.safe_upsert_user_attribution(
            user_id=user.id,
            telegram_id=user.telegram_id,
            source_type=analytics.SOURCE_TYPE_CHANNEL_POST,
            source_key="inst_reels_april_01",
            channel_item_id=None,
            seen_at=base_time + timedelta(hours=1),
        )
        await analytics.emit_analytics_event(
            event_name=analytics.EVENT_BOT_START,
            user_id=user.id,
            telegram_id=user.telegram_id,
            dedupe_key="fallback:bot-start:205",
            occurred_at=base_time + timedelta(days=1),
            payload={
                "source_type": analytics.SOURCE_TYPE_CHANNEL_POST,
                "source_key": "inst_reels_april_01",
                "channel_item_id": None,
            },
        )

        await analytics.backfill_analytics_user_attribution()
        await analytics.refresh_analytics_rollups(force_full=True)

        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(AnalyticsUserAttribution).where(AnalyticsUserAttribution.user_id == user.id)
                )
            ).scalar_one()
            stage_rows = list((await session.execute(select(AnalyticsDailyStageCount))).scalars().all())

        self.assertEqual(row.first_source_key, analytics.SOURCE_TYPE_ORGANIC)
        self.assertEqual(row.last_source_key, "inst_reels_april_01")
        self.assertTrue(
            any(
                stage_row.event_name == analytics.EVENT_BOT_START
                and stage_row.source_mode == analytics.SOURCE_MODE_LAST
                and stage_row.source_key == "inst_reels_april_01"
                for stage_row in stage_rows
            )
        )

    async def test_backfill_attribution_replaces_fresh_organic_first_for_new_tracked_user(self) -> None:
        base_time = datetime(2026, 4, 6, 10, 0, 0)
        async with self.session_factory() as session:
            user = User(
                telegram_id=206,
                username="fresh_user",
                preferred_protocol="vless",
                subscription_status="inactive",
                trial_activity_level="low",
                created_at=base_time,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        await analytics.upsert_user_attribution(
            user_id=user.id,
            telegram_id=user.telegram_id,
            source_type=analytics.SOURCE_TYPE_ORGANIC,
            source_key=analytics.SOURCE_TYPE_ORGANIC,
            seen_at=base_time,
        )
        await analytics.emit_analytics_event(
            event_name=analytics.EVENT_LINK_TOUCHED,
            user_id=user.id,
            telegram_id=user.telegram_id,
            dedupe_key="fresh:link-touch:206",
            occurred_at=base_time + timedelta(seconds=30),
            payload={
                "source_type": analytics.SOURCE_TYPE_CHANNEL_POST,
                "source_key": "inst_reels_april_01",
                "channel_item_id": None,
            },
        )
        await analytics.safe_upsert_user_attribution(
            user_id=user.id,
            telegram_id=user.telegram_id,
            source_type=analytics.SOURCE_TYPE_CHANNEL_POST,
            source_key="inst_reels_april_01",
            channel_item_id=None,
            seen_at=base_time + timedelta(hours=1),
        )
        await analytics.emit_analytics_event(
            event_name=analytics.EVENT_BOT_START,
            user_id=user.id,
            telegram_id=user.telegram_id,
            dedupe_key="fresh:bot-start:206",
            occurred_at=base_time + timedelta(seconds=45),
            payload={
                "source_type": analytics.SOURCE_TYPE_CHANNEL_POST,
                "source_key": "inst_reels_april_01",
                "channel_item_id": None,
            },
        )

        await analytics.backfill_analytics_user_attribution()

        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(AnalyticsUserAttribution).where(AnalyticsUserAttribution.user_id == user.id)
                )
            ).scalar_one()

        self.assertEqual(row.first_source_key, "inst_reels_april_01")
        self.assertEqual(row.last_source_key, "inst_reels_april_01")

    async def test_refresh_does_not_reassign_old_bot_start_to_new_last_source(self) -> None:
        first_seen = datetime(2026, 4, 6, 9, 0, 0)
        revisit_seen = first_seen + timedelta(days=1)
        async with self.session_factory() as session:
            user = User(
                telegram_id=207,
                username="revisit_user",
                preferred_protocol="vless",
                subscription_status="inactive",
                trial_activity_level="low",
                created_at=first_seen,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            session.add(
                AnalyticsEvent(
                    occurred_at=first_seen,
                    user_id=user.id,
                    telegram_id=user.telegram_id,
                    event_name=analytics.EVENT_BOT_START,
                    dedupe_key="revisit:old-start",
                    payload_json='{"source_type":"organic_bot","source_key":"organic_bot"}',
                    created_at=first_seen,
                )
            )
            session.add(
                AnalyticsEvent(
                    occurred_at=revisit_seen,
                    user_id=user.id,
                    telegram_id=user.telegram_id,
                    event_name=analytics.EVENT_BOT_START,
                    dedupe_key="revisit:new-start",
                    payload_json='{"source_type":"channel_post","source_key":"campaign-later"}',
                    created_at=revisit_seen,
                )
            )
            await session.commit()

        await analytics.upsert_user_attribution(
            user_id=user.id,
            telegram_id=user.telegram_id,
            source_type=analytics.SOURCE_TYPE_ORGANIC,
            source_key=analytics.SOURCE_TYPE_ORGANIC,
            seen_at=first_seen,
        )
        await analytics.upsert_user_attribution(
            user_id=user.id,
            telegram_id=user.telegram_id,
            source_type=analytics.SOURCE_TYPE_CHANNEL_POST,
            source_key="campaign-later",
            seen_at=revisit_seen,
        )

        await analytics.refresh_analytics_rollups(force_full=True)

        async with self.session_factory() as session:
            stage_rows = list(
                (
                    await session.execute(
                        select(AnalyticsDailyStageCount).where(
                            AnalyticsDailyStageCount.event_name == analytics.EVENT_BOT_START
                        )
                    )
                ).scalars().all()
            )

        self.assertFalse(
            any(
                row.bucket_date == first_seen.date()
                and row.source_mode == analytics.SOURCE_MODE_LAST
                and row.source_key == "campaign-later"
                for row in stage_rows
            )
        )
        self.assertTrue(
            any(
                row.bucket_date == first_seen.date()
                and row.source_mode == analytics.SOURCE_MODE_FIRST
                and row.source_key == analytics.SOURCE_TYPE_ORGANIC
                and row.users_count == 1
                for row in stage_rows
            )
        )
        self.assertTrue(
            any(
                row.bucket_date == revisit_seen.date()
                and row.source_mode == analytics.SOURCE_MODE_LAST
                and row.source_key == "campaign-later"
                and row.users_count == 1
                for row in stage_rows
            )
        )

    async def test_emit_event_captures_event_time_first_and_last_attribution_snapshots(self) -> None:
        first_seen = datetime(2026, 4, 6, 8, 0, 0)
        revisit_seen = first_seen + timedelta(days=1)
        async with self.session_factory() as session:
            user = User(
                telegram_id=208,
                username="snapshot_user",
                preferred_protocol="vless",
                subscription_status="inactive",
                trial_activity_level="low",
                created_at=first_seen,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        await analytics.upsert_user_attribution(
            user_id=user.id,
            telegram_id=user.telegram_id,
            source_type=analytics.SOURCE_TYPE_ORGANIC,
            source_key=analytics.SOURCE_TYPE_ORGANIC,
            seen_at=first_seen,
        )
        await analytics.upsert_user_attribution(
            user_id=user.id,
            telegram_id=user.telegram_id,
            source_type=analytics.SOURCE_TYPE_CHANNEL_POST,
            source_key="campaign-snap",
            seen_at=revisit_seen,
        )
        await analytics.emit_analytics_event(
            event_name=analytics.EVENT_PAYMENT_SUCCESS,
            user_id=user.id,
            telegram_id=user.telegram_id,
            occurred_at=revisit_seen,
            dedupe_key="snapshot:payment",
            payload={"amount_rub": 399, "product_type": "subscription"},
        )

        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(AnalyticsEvent).where(AnalyticsEvent.dedupe_key == "snapshot:payment")
                )
            ).scalar_one()

        payload = analytics._safe_json_loads(row.payload_json)
        self.assertEqual(payload["attribution_first"]["source_key"], analytics.SOURCE_TYPE_ORGANIC)
        self.assertEqual(payload["attribution_last"]["source_key"], "campaign-snap")

    async def test_backfill_and_refresh_generate_rollups_for_real_users_only(self) -> None:
        base_time = datetime(2026, 4, 4, 9, 0, 0)
        async with self.session_factory() as session:
            user = User(
                telegram_id=301,
                username="channel_user",
                preferred_protocol="vless",
                subscription_status="vip_active",
                trial_started_at=base_time + timedelta(minutes=15),
                subscription_started_at=base_time,
                subscription_expires_at=base_time + timedelta(days=30),
                trial_activity_level="high",
                created_at=base_time,
            )
            synthetic_user = User(
                telegram_id=302,
                username="bridge_noise",
                preferred_protocol="vless",
                subscription_status="inactive",
                trial_activity_level="low",
                created_at=base_time,
            )
            item = ChannelContentItem(
                content_type="daily_news",
                topic_brief="VPN post",
                status="published",
                scheduled_at=base_time,
                published_at=base_time,
                deep_link_token="tracked-token",
            )
            session.add_all([user, synthetic_user, item])
            await session.commit()
            await session.refresh(user)
            await session.refresh(item)

            session.add(
                ChannelPostTouch(
                    item_id=item.id,
                    user_id=user.id,
                    telegram_id=user.telegram_id,
                    first_seen_at=base_time,
                    last_seen_at=base_time,
                    converted_at=base_time + timedelta(minutes=30),
                    conversion_reason="trial_started",
                )
            )
            payment = PaymentRecord(
                user_id=user.id,
                external_payment_id="ext-301",
                tariff_code="1m",
                payment_method="sbp_platega",
                payment_status="confirmed",
                amount=399,
                list_price_amount=399,
                currency="RUB",
                duration_days=30,
                confirmed_at=base_time + timedelta(hours=1),
                created_at=base_time + timedelta(minutes=45),
            )
            vpn_client = VpnClient(
                user_id=user.id,
                protocol="vless",
                client_uuid="uuid-301",
                email="user301@example.com",
                created_at=base_time + timedelta(hours=2),
            )
            session.add_all([payment, vpn_client])
            await session.commit()
            await session.refresh(payment)
            await session.refresh(vpn_client)
            session.add(
                VpnClientActivation(
                    vpn_client_id=vpn_client.id,
                    user_id=user.id,
                    country_code="de",
                    fingerprint_hash="f" * 64,
                    first_activated_at=base_time + timedelta(hours=2, minutes=5),
                    last_activated_at=base_time + timedelta(hours=2, minutes=5),
                )
            )
            await session.commit()

        attribution_result = await analytics.backfill_analytics_user_attribution()
        events_result = await analytics.backfill_analytics_events()
        refresh_result = await analytics.refresh_analytics_rollups(force_full=True)

        async with self.session_factory() as session:
            stage_rows = list((await session.execute(select(AnalyticsDailyStageCount))).scalars().all())
            stage_segment_rows = list((await session.execute(select(AnalyticsDailyStageSegment))).scalars().all())
            revenue_rows = list((await session.execute(select(AnalyticsDailyRevenue))).scalars().all())
            revenue_segment_rows = list((await session.execute(select(AnalyticsDailyRevenueSegment))).scalars().all())
            connection_rows = list((await session.execute(select(AnalyticsDailyConnection))).scalars().all())
            cohort_rows = list((await session.execute(select(AnalyticsCohortRetention))).scalars().all())
            payment_failure_rows = list(
                (await session.execute(select(AnalyticsDailyPaymentFailureReason))).scalars().all()
            )
            attribution_integrity_rows = list(
                (await session.execute(select(AnalyticsDailyAttributionIntegrity))).scalars().all()
            )
            runtime_rows = list((await session.execute(select(AnalyticsRuntimeStatus))).scalars().all())

        self.assertGreaterEqual(attribution_result["attributed"], 1)
        self.assertGreaterEqual(events_result.get(analytics.EVENT_BOT_START, 0), 1)
        self.assertGreaterEqual(events_result.get(analytics.EVENT_CHANNEL_MEMBERSHIP_CONFIRMED, 0), 1)
        self.assertGreaterEqual(events_result.get(analytics.EVENT_CONNECTION_READY, 0), 1)
        self.assertGreaterEqual(events_result.get(analytics.EVENT_SUBSCRIPTION_ACTIVATED, 0), 1)
        self.assertGreaterEqual(events_result.get(analytics.EVENT_PAYMENT_SUCCESS, 0), 1)
        self.assertGreaterEqual(events_result.get(analytics.EVENT_FIRST_CONNECTION_SUCCESS, 0), 1)
        self.assertGreaterEqual(refresh_result["dates_refreshed"], 1)
        self.assertTrue(
            any(
                row.source_mode == "first"
                and row.source_key == "tracked-token"
                and row.event_name == analytics.EVENT_LINK_TOUCHED
                for row in stage_rows
            )
        )
        self.assertTrue(
            any(
                row.source_mode == "last"
                and row.source_key == "tracked-token"
                and row.event_name == analytics.EVENT_LINK_TOUCHED
                for row in stage_rows
            )
        )
        self.assertTrue(any(row.event_name == analytics.EVENT_CHANNEL_MEMBERSHIP_CONFIRMED for row in stage_rows))
        self.assertTrue(any(row.event_name == analytics.EVENT_CONNECTION_READY for row in stage_rows))
        self.assertTrue(any(row.user_segment == analytics.USER_SEGMENT_NEW for row in stage_segment_rows))
        self.assertTrue(any(row.revenue_amount_rub == 399 and row.payment_kind == analytics.PAYMENT_KIND_NEW for row in revenue_rows))
        self.assertTrue(
            any(
                row.user_segment == analytics.USER_SEGMENT_NEW
                and row.revenue_amount_rub == 399
                and row.payment_kind == analytics.PAYMENT_KIND_NEW
                for row in revenue_segment_rows
            )
        )
        self.assertTrue(any(row.country_code == "de" and row.first_connection_success_count == 1 for row in connection_rows))
        self.assertTrue(any(row.active_users >= 1 for row in cohort_rows))
        self.assertEqual(payment_failure_rows, [])
        self.assertEqual(attribution_integrity_rows, [])
        self.assertTrue(any(row.status_key == analytics.RUNTIME_STATUS_SOURCE_KEY_INTEGRITY for row in runtime_rows))
        self.assertTrue(any(row.status_key == analytics.RUNTIME_STATUS_GROWTH_ACTIVE_USERS for row in runtime_rows))

    async def test_refresh_builds_payment_failure_and_attribution_integrity_rollups(self) -> None:
        base_time = datetime(2026, 4, 6, 10, 0, 0)
        async with self.session_factory() as session:
            user_ok = User(
                telegram_id=601,
                username="campaign_user",
                preferred_protocol="vless",
                subscription_status="inactive",
                trial_activity_level="low",
                created_at=base_time,
            )
            user_bad = User(
                telegram_id=602,
                username="bad_attribution_user",
                preferred_protocol="vless",
                subscription_status="inactive",
                trial_activity_level="low",
                created_at=base_time,
            )
            session.add_all([user_ok, user_bad])
            await session.commit()
            await session.refresh(user_ok)
            await session.refresh(user_bad)

        await analytics.emit_analytics_event(
            event_name=analytics.EVENT_BOT_START,
            user_id=user_ok.id,
            telegram_id=user_ok.telegram_id,
            dedupe_key="failure:good:start",
            occurred_at=base_time,
            payload={
                "source_type": analytics.SOURCE_TYPE_CHANNEL_POST,
                "source_key": "campaign-beta",
            },
        )
        await analytics.emit_analytics_event(
            event_name=analytics.EVENT_PAYMENT_FAILED,
            user_id=user_ok.id,
            telegram_id=user_ok.telegram_id,
            dedupe_key="failure:good:payment",
            occurred_at=base_time + timedelta(hours=1),
            payload={
                "source_type": analytics.SOURCE_TYPE_CHANNEL_POST,
                "source_key": "campaign-beta",
                "product_type": "subscription",
                "payment_status": "rejected",
                "review_source": "dashboard",
                "rejection_reason": "Отклонено из панели",
            },
            payment_method="sbp_manual",
        )
        await analytics.emit_analytics_event(
            event_name=analytics.EVENT_BOT_START,
            user_id=user_bad.id,
            telegram_id=user_bad.telegram_id,
            dedupe_key="integrity:bad:start",
            occurred_at=base_time + timedelta(minutes=5),
            payload={},
        )

        refresh_result = await analytics.refresh_analytics_rollups(force_full=True)

        async with self.session_factory() as session:
            failure_rows = list(
                (
                    await session.execute(
                        select(AnalyticsDailyPaymentFailureReason).where(
                            AnalyticsDailyPaymentFailureReason.bucket_date == base_time.date()
                        )
                    )
                ).scalars().all()
            )
            integrity_rows = list(
                (
                    await session.execute(
                        select(AnalyticsDailyAttributionIntegrity).where(
                            AnalyticsDailyAttributionIntegrity.bucket_date == base_time.date()
                        )
                    )
                ).scalars().all()
            )

        self.assertGreaterEqual(refresh_result["dates_refreshed"], 1)
        self.assertTrue(
            any(
                row.reason_key == "manual_rejected"
                and row.failures_count == 1
                and row.source_key == "campaign-beta"
                for row in failure_rows
            )
        )
        self.assertTrue(
            any(
                row.issue_type == analytics.ATTRIBUTION_ISSUE_MISSING_SOURCE
                and row.issue_count == 1
                and row.affected_users_count == 1
                and row.total_bot_start_count >= 2
                for row in integrity_rows
            )
        )

    async def test_refresh_builds_new_vs_returning_segment_rollups(self) -> None:
        first_day = datetime(2026, 4, 1, 9, 0, 0)
        second_day = datetime(2026, 4, 2, 9, 0, 0)
        async with self.session_factory() as session:
            new_user = User(
                telegram_id=501,
                username="new_user",
                preferred_protocol="vless",
                subscription_status="active",
                subscription_started_at=second_day,
                subscription_expires_at=second_day + timedelta(days=30),
                trial_activity_level="high",
                created_at=second_day,
            )
            returning_user = User(
                telegram_id=502,
                username="returning_user",
                preferred_protocol="vless",
                subscription_status="active",
                subscription_started_at=first_day,
                subscription_expires_at=first_day + timedelta(days=30),
                trial_activity_level="high",
                created_at=first_day,
            )
            session.add_all([new_user, returning_user])
            await session.commit()
            await session.refresh(new_user)
            await session.refresh(returning_user)

        await analytics.emit_analytics_event(
            event_name=analytics.EVENT_BOT_START,
            user_id=returning_user.id,
            telegram_id=returning_user.telegram_id,
            dedupe_key="segment:returning:first-start",
            occurred_at=first_day,
            payload={"source_type": analytics.SOURCE_TYPE_CHANNEL_POST, "source_key": "campaign-alpha"},
        )
        await analytics.emit_analytics_event(
            event_name=analytics.EVENT_BOT_START,
            user_id=new_user.id,
            telegram_id=new_user.telegram_id,
            dedupe_key="segment:new:start",
            occurred_at=second_day,
            payload={"source_type": analytics.SOURCE_TYPE_CHANNEL_POST, "source_key": "campaign-alpha"},
        )
        await analytics.emit_analytics_event(
            event_name=analytics.EVENT_PAYMENT_SUCCESS,
            user_id=new_user.id,
            telegram_id=new_user.telegram_id,
            dedupe_key="segment:new:paid",
            occurred_at=second_day + timedelta(hours=1),
            payload={
                "source_type": analytics.SOURCE_TYPE_CHANNEL_POST,
                "source_key": "campaign-alpha",
                "amount_rub": 399,
                "product_type": "subscription",
                "payment_kind": analytics.PAYMENT_KIND_NEW,
            },
            payment_method="sbp_platega",
            tariff_code="1m",
        )
        await analytics.emit_analytics_event(
            event_name=analytics.EVENT_PAYMENT_SUCCESS,
            user_id=returning_user.id,
            telegram_id=returning_user.telegram_id,
            dedupe_key="segment:returning:paid",
            occurred_at=second_day + timedelta(hours=2),
            payload={
                "source_type": analytics.SOURCE_TYPE_CHANNEL_POST,
                "source_key": "campaign-alpha",
                "amount_rub": 799,
                "product_type": "subscription",
                "payment_kind": analytics.PAYMENT_KIND_RENEWAL,
            },
            payment_method="sbp_platega",
            tariff_code="3m",
        )

        refresh_result = await analytics.refresh_analytics_rollups(force_full=True)

        async with self.session_factory() as session:
            stage_segment_rows = list(
                (
                    await session.execute(
                        select(AnalyticsDailyStageSegment).where(
                            AnalyticsDailyStageSegment.bucket_date == second_day.date(),
                            AnalyticsDailyStageSegment.event_name == analytics.EVENT_BOT_START,
                        )
                    )
                ).scalars().all()
            )
            revenue_segment_rows = list(
                (
                    await session.execute(
                        select(AnalyticsDailyRevenueSegment).where(
                            AnalyticsDailyRevenueSegment.bucket_date == second_day.date()
                        )
                    )
                ).scalars().all()
            )

        self.assertGreaterEqual(refresh_result["dates_refreshed"], 2)
        self.assertTrue(any(row.user_segment == analytics.USER_SEGMENT_NEW and row.users_count == 1 for row in stage_segment_rows))
        self.assertFalse(any(row.user_segment == analytics.USER_SEGMENT_RETURNING for row in stage_segment_rows))
        self.assertTrue(
            any(
                row.user_segment == analytics.USER_SEGMENT_NEW
                and row.revenue_amount_rub == 399
                and row.payment_kind == analytics.PAYMENT_KIND_NEW
                for row in revenue_segment_rows
            )
        )
        self.assertTrue(
            any(
                row.user_segment == analytics.USER_SEGMENT_RETURNING
                and row.revenue_amount_rub == 799
                and row.payment_kind == analytics.PAYMENT_KIND_RENEWAL
                for row in revenue_segment_rows
            )
        )

    async def test_ops_refresh_builds_hourly_rollups_and_runtime_status(self) -> None:
        now = datetime(2026, 4, 5, 8, 30, 0)
        async with self.session_factory() as session:
            repair_user = User(
                telegram_id=401,
                username="ops_user",
                preferred_protocol="vless",
                subscription_status="vip_active",
                trial_activity_level="high",
                vpn_repair_needed=True,
                vpn_repair_reason="payment_activation_issue",
                vpn_repair_marked_at=now - timedelta(hours=2),
                created_at=now - timedelta(days=10),
            )
            synthetic_user = User(
                telegram_id=402,
                username="bridge_noise",
                preferred_protocol="vless",
                subscription_status="inactive",
                trial_activity_level="low",
                vpn_repair_needed=True,
                vpn_repair_reason="payment_activation_issue",
                created_at=now - timedelta(days=1),
            )
            session.add_all([repair_user, synthetic_user])
            await session.commit()
            await session.refresh(repair_user)

            session.add_all(
                [
                    ControlNotificationEvent(
                        category="access",
                        severity="CRITICAL",
                        event_type="user_access_issue",
                        title="Access issue",
                        message="Repair needed",
                        entity_type="users",
                        entity_id=str(repair_user.id),
                        created_at=now - timedelta(minutes=50),
                        repeat_count=2,
                    ),
                    ControlNotificationEvent(
                        category="errors",
                        severity="WARNING",
                        event_type="service_health_issue",
                        title="Service warning",
                        message="Service degraded",
                        entity_type="service",
                        entity_id="amonora-bot.service",
                        created_at=now - timedelta(minutes=30),
                        resolved_at=now - timedelta(minutes=10),
                        repeat_count=1,
                    ),
                    ControlNotificationEvent(
                        category="access",
                        severity="WARNING",
                        event_type="access_provisioning_failed",
                        title="Provisioning failure",
                        message="Provisioning failure",
                        entity_type="user",
                        entity_id=str(repair_user.id),
                        created_at=now - timedelta(hours=1),
                    ),
                ]
            )
            await session.commit()

        with tempfile.TemporaryDirectory() as tmpdir:
            proof_path = Path(tmpdir) / "restore-proof.json"
            proof_path.write_text(
                '{"proof_kind":"temporary_database_restore","proof_status":"verified","proof_scope":["core_pg"],"verified_at":"2026-04-05T08:20:00"}',
                encoding="utf-8",
            )
            with patch.object(analytics, "RESTORE_PROOF_STATUS_PATH", proof_path), patch.object(analytics, "_utcnow", return_value=now):
                result = await analytics.refresh_ops_analytics_rollups(force_full=True)

        async with self.session_factory() as session:
            incident_rows = list((await session.execute(select(AnalyticsHourlyOpsIncident))).scalars().all())
            snapshot_rows = list((await session.execute(select(AnalyticsHourlyOpsSnapshot))).scalars().all())
            runtime_rows = list((await session.execute(select(AnalyticsRuntimeStatus))).scalars().all())

        self.assertGreaterEqual(result["hours_refreshed"], 1)
        self.assertTrue(any(row.event_type == "user_access_issue" and row.created_count == 1 for row in incident_rows))
        self.assertTrue(any(row.event_type == "service_health_issue" and row.resolved_count == 1 for row in incident_rows))
        self.assertTrue(any(row.repair_needed_open_count == 1 for row in snapshot_rows))
        self.assertTrue(any(row.status_key == analytics.RUNTIME_STATUS_RESTORE_PROOF and row.status_value == "healthy" for row in runtime_rows))
        self.assertTrue(any(row.status_key == analytics.RUNTIME_STATUS_REPAIR_OPEN for row in runtime_rows))


if __name__ == "__main__":
    unittest.main()
