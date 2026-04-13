import unittest

from bot.repair_reasons import (
    AUTO_REPAIR_FAILED,
    MANUAL_REPAIR,
    MANUAL_REPAIR_NO_ACCESS,
    MANUAL_REPAIR_NO_DEVICES,
    MANUAL_REPAIR_SYNC_FAILED,
    POST_PAYMENT_ACCESS_INCOMPLETE,
    POST_PAYMENT_SYNC_FAILED,
    normalize_repair_event_reason,
    normalize_repair_outcome,
    normalize_repair_source,
    normalize_repair_reason,
    repair_outcome_label,
    repair_reason_category,
    repair_reason_label,
    repair_source_label,
)


class RepairReasonNormalizationTests(unittest.TestCase):
    def test_normalize_repair_reason_maps_legacy_manual_aliases(self) -> None:
        self.assertEqual(normalize_repair_reason("manual_repair_failed"), MANUAL_REPAIR_SYNC_FAILED)
        self.assertEqual(normalize_repair_reason("manual_repair_failed_no_access"), MANUAL_REPAIR_NO_ACCESS)
        self.assertEqual(normalize_repair_reason("manual_repair_failed_no_devices"), MANUAL_REPAIR_NO_DEVICES)

    def test_repair_reason_label_returns_human_readable_labels(self) -> None:
        self.assertEqual(repair_reason_label(POST_PAYMENT_SYNC_FAILED), "Post-payment VPN sync failed")
        self.assertEqual(repair_reason_label(POST_PAYMENT_ACCESS_INCOMPLETE), "Post-payment access incomplete")
        self.assertEqual(repair_reason_label(MANUAL_REPAIR_SYNC_FAILED), "Manual repair sync failed")
        self.assertEqual(repair_reason_label(MANUAL_REPAIR_NO_ACCESS), "Manual repair skipped: no active access")
        self.assertEqual(repair_reason_label(MANUAL_REPAIR_NO_DEVICES), "Manual repair skipped: no devices")
        self.assertEqual(repair_reason_label(AUTO_REPAIR_FAILED), "Auto-retry failed to recover the VPN sync")

    def test_repair_reason_category_groups_canonical_reasons(self) -> None:
        self.assertEqual(repair_reason_category(POST_PAYMENT_SYNC_FAILED), "payment_related")
        self.assertEqual(repair_reason_category(MANUAL_REPAIR_SYNC_FAILED), "manual_repair")
        self.assertEqual(repair_reason_category(MANUAL_REPAIR_NO_ACCESS), "manual_repair")

    def test_repair_source_and_outcome_normalize_event_semantics(self) -> None:
        self.assertEqual(normalize_repair_source(MANUAL_REPAIR_SYNC_FAILED), "manual")
        self.assertEqual(normalize_repair_source(POST_PAYMENT_SYNC_FAILED), "post_payment")
        self.assertEqual(repair_source_label(MANUAL_REPAIR_SYNC_FAILED), "Manual")
        self.assertEqual(normalize_repair_outcome("failed", MANUAL_REPAIR_NO_DEVICES), "skipped")
        self.assertEqual(normalize_repair_outcome("success", MANUAL_REPAIR), "success")
        self.assertEqual(repair_outcome_label("failed", MANUAL_REPAIR_NO_ACCESS), "Skipped")
        self.assertIsNone(normalize_repair_event_reason(MANUAL_REPAIR, "success"))


if __name__ == "__main__":
    unittest.main()
