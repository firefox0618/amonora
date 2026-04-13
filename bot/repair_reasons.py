POST_PAYMENT_SYNC_FAILED = "post_payment_sync_failed"
POST_PAYMENT_ACCESS_INCOMPLETE = "post_payment_access_incomplete"
MANUAL_REPAIR_SYNC_FAILED = "manual_repair_sync_failed"
MANUAL_REPAIR_NO_ACCESS = "manual_repair_no_access"
MANUAL_REPAIR_NO_DEVICES = "manual_repair_no_devices"
MANUAL_REPAIR = "manual_repair"
AUTO_REPAIR_SUCCESS = "auto_repair_success"
AUTO_REPAIR_FAILED = "auto_repair_failed"

PERSISTENT_REPAIR_REASONS = (
    POST_PAYMENT_SYNC_FAILED,
    POST_PAYMENT_ACCESS_INCOMPLETE,
    MANUAL_REPAIR_SYNC_FAILED,
    MANUAL_REPAIR_NO_ACCESS,
    MANUAL_REPAIR_NO_DEVICES,
)

EVENT_ONLY_REPAIR_REASONS = (
    MANUAL_REPAIR,
    AUTO_REPAIR_SUCCESS,
    AUTO_REPAIR_FAILED,
)

LEGACY_REPAIR_REASON_ALIASES = {
    "manual_repair_failed": MANUAL_REPAIR_SYNC_FAILED,
    "manual_repair_failed_no_access": MANUAL_REPAIR_NO_ACCESS,
    "manual_repair_failed_no_devices": MANUAL_REPAIR_NO_DEVICES,
}

REPAIR_REASON_LABELS = {
    POST_PAYMENT_SYNC_FAILED: "Post-payment VPN sync failed",
    POST_PAYMENT_ACCESS_INCOMPLETE: "Post-payment access incomplete",
    MANUAL_REPAIR_SYNC_FAILED: "Manual repair sync failed",
    MANUAL_REPAIR_NO_ACCESS: "Manual repair skipped: no active access",
    MANUAL_REPAIR_NO_DEVICES: "Manual repair skipped: no devices",
    AUTO_REPAIR_SUCCESS: "Auto-retry recovered the VPN sync",
    AUTO_REPAIR_FAILED: "Auto-retry failed to recover the VPN sync",
}

REPAIR_SOURCE_LABELS = {
    "post_payment": "Post-payment",
    "manual": "Manual",
    "auto": "Auto-retry",
    "unknown": "Unknown",
}

REPAIR_OUTCOME_LABELS = {
    "success": "Succeeded",
    "failed": "Failed",
    "skipped": "Skipped",
    "unknown": "Unknown",
}


def normalize_repair_reason(reason: str | None) -> str | None:
    if not reason:
        return reason
    return LEGACY_REPAIR_REASON_ALIASES.get(reason, reason)


def repair_reason_label(reason: str | None) -> str | None:
    normalized = normalize_repair_reason(reason)
    if not normalized:
        return None
    return REPAIR_REASON_LABELS.get(normalized, normalized.replace("_", " "))


def normalize_repair_source(reason: str | None) -> str:
    normalized = normalize_repair_reason(reason)
    if not normalized:
        return "unknown"
    if normalized.startswith("post_payment_") or normalized.startswith("payment_finalization_"):
        return "post_payment"
    if normalized == MANUAL_REPAIR or normalized.startswith("manual_repair_"):
        return "manual"
    if normalized.startswith("auto_repair_"):
        return "auto"
    return "unknown"


def repair_source_label(reason: str | None) -> str:
    return REPAIR_SOURCE_LABELS.get(normalize_repair_source(reason), "Unknown")


def normalize_repair_outcome(result: str | None, reason: str | None = None) -> str:
    normalized_reason = normalize_repair_reason(reason)
    if normalized_reason in {MANUAL_REPAIR_NO_ACCESS, MANUAL_REPAIR_NO_DEVICES}:
        return "skipped"
    if result in {"success", "failed", "skipped"}:
        return result
    return "unknown"


def repair_outcome_label(result: str | None, reason: str | None = None) -> str:
    return REPAIR_OUTCOME_LABELS.get(normalize_repair_outcome(result, reason), "Unknown")


def normalize_repair_event_reason(reason: str | None, result: str | None = None) -> str | None:
    normalized = normalize_repair_reason(reason)
    if normalized in {MANUAL_REPAIR, AUTO_REPAIR_SUCCESS, AUTO_REPAIR_FAILED}:
        return None
    return normalized


def normalize_repair_event_reason_label(reason: str | None, result: str | None = None) -> str | None:
    normalized = normalize_repair_event_reason(reason, result)
    if not normalized:
        return None
    return repair_reason_label(normalized)


def is_payment_related_repair_reason(reason: str | None) -> bool:
    normalized = normalize_repair_reason(reason)
    if not normalized:
        return False
    return normalized.startswith("post_payment_") or normalized.startswith("payment_finalization_")


def repair_reason_category(reason: str | None) -> str:
    normalized = normalize_repair_reason(reason)
    if not normalized:
        return "unknown"
    if normalized.startswith("post_payment_") or normalized.startswith("payment_finalization_"):
        return "payment_related"
    if normalized.startswith("manual_repair_"):
        return "manual_repair"
    if normalized.startswith("access_") or normalized.endswith("_no_access") or "access" in normalized:
        return "access_state"
    if "sync" in normalized:
        return "sync"
    return "other"
