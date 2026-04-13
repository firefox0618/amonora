import json
import unittest

from datetime import datetime
from types import SimpleNamespace

from dashboard.v2_data import _serialize_audit_log


class DashboardAuditDisplaySummaryTests(unittest.TestCase):
    def test_reject_payment_record_summary_is_compact(self) -> None:
        raw_details = json.dumps(
            {
                "reason": "Отклонено из панели",
                "before": {
                    "payment_status": "awaiting_admin_review",
                    "reviewed_by_actor_name": None,
                },
                "after": {
                    "payment_status": "rejected",
                    "reviewed_by_actor_name": "Rudolf",
                    "rejection_reason": "Отклонено из панели",
                },
            },
            ensure_ascii=False,
        )
        item = SimpleNamespace(
            id=176,
            admin_id=7,
            action="reject_payment_record",
            target_type="payment_record",
            target_id="176",
            details_text=raw_details,
            request_id="req-176",
            created_at=datetime(2026, 4, 5, 19, 15),
        )

        payload = _serialize_audit_log(item, {7: SimpleNamespace(display_name="Rudolf")})

        self.assertEqual(payload["details_text"], "Статус: Ожидает проверку → Отклонён · Причина: Отклонено из панели")
        self.assertEqual(payload["raw_details_text"], raw_details)

    def test_close_support_ticket_summary_shows_only_status_and_notification(self) -> None:
        raw_details = json.dumps(
            {
                "user_notified": True,
                "before": {
                    "status": "in_progress",
                    "assigned_admin_name": "Dexus @dextrmed",
                },
                "after": {
                    "status": "closed",
                    "assigned_admin_name": "Dexus @dextrmed",
                },
            },
            ensure_ascii=False,
        )
        item = SimpleNamespace(
            id=98,
            admin_id=4,
            action="close_support_ticket",
            target_type="support_ticket",
            target_id="7563312212",
            details_text=raw_details,
            request_id="req-98",
            created_at=datetime(2026, 4, 5, 19, 17),
        )

        payload = _serialize_audit_log(item, {4: SimpleNamespace(display_name="Rudolf")})

        self.assertEqual(payload["details_text"], "Статус: В работе → Закрыто · Пользователь уведомлён")
        self.assertEqual(payload["raw_details_text"], raw_details)

    def test_plain_text_details_remain_searchable(self) -> None:
        item = SimpleNamespace(
            id=12,
            admin_id=None,
            action="server_health_check",
            target_type="server",
            target_id="de-1",
            details_text="Проверка выполнена успешно, отклонений не найдено.",
            request_id=None,
            created_at=datetime(2026, 4, 5, 20, 0),
        )

        payload = _serialize_audit_log(item, {})

        self.assertEqual(payload["details_text"], "Проверка выполнена успешно, отклонений не найдено.")
        self.assertEqual(payload["raw_details_text"], "Проверка выполнена успешно, отклонений не найдено.")


if __name__ == "__main__":
    unittest.main()
