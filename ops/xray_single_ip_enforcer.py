from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import subprocess

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


LOG_LINE_RE = re.compile(
    r"^(?P<stamp>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})(?:\.\d+)?\s+from\s+(?P<ip>[0-9a-fA-F:\.]+):\d+.*?\bemail:\s*(?P<email>\S+)\s*$"
)
DEFAULT_MANAGED_PREFIXES = ("device_", "dashboard_", "landing_bridge_")
DEFAULT_IGNORED_PREFIXES = ("test_",)
DEFAULT_IGNORED_EMAILS = ("dk-main",)


@dataclass(frozen=True)
class AccessEvent:
    occurred_at: datetime
    ip: str
    email: str


def utcnow() -> datetime:
    return datetime.now(UTC)


def parse_access_log_line(line: str) -> AccessEvent | None:
    match = LOG_LINE_RE.search(line.strip())
    if not match:
        return None
    occurred_at = datetime.strptime(match.group("stamp"), "%Y/%m/%d %H:%M:%S").replace(tzinfo=UTC)
    return AccessEvent(
        occurred_at=occurred_at,
        ip=match.group("ip"),
        email=match.group("email"),
    )


def is_enforceable_ip(value: str) -> bool:
    normalized = str(value or "").strip()
    if not normalized:
        return False
    try:
        parsed = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return not parsed.is_unspecified


def is_managed_email(
    email: str,
    *,
    managed_prefixes: tuple[str, ...],
    ignored_prefixes: tuple[str, ...],
    ignored_emails: tuple[str, ...],
) -> bool:
    normalized = str(email or "").strip()
    if not normalized:
        return False
    if normalized in ignored_emails:
        return False
    if any(normalized.startswith(prefix) for prefix in ignored_prefixes):
        return False
    return any(normalized.startswith(prefix) for prefix in managed_prefixes)


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return json.loads(json.dumps(default))
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return json.loads(json.dumps(default))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


def _read_access_events(access_log_path: Path, state: dict[str, Any], *, first_run_bytes: int) -> tuple[list[AccessEvent], dict[str, Any]]:
    file_state = state.setdefault("file", {})
    current_inode = None
    current_size = 0
    if access_log_path.exists():
        stat = access_log_path.stat()
        current_inode = int(stat.st_ino)
        current_size = int(stat.st_size)

    offset = int(file_state.get("offset", 0) or 0)
    previous_inode = file_state.get("inode")
    if current_inode is None:
        file_state["inode"] = None
        file_state["offset"] = 0
        return [], state
    if previous_inode != current_inode or offset > current_size:
        offset = max(current_size - max(int(first_run_bytes), 0), 0)

    events: list[AccessEvent] = []
    with access_log_path.open("r", encoding="utf-8", errors="ignore") as handle:
        handle.seek(offset)
        for raw_line in handle:
            event = parse_access_log_line(raw_line)
            if event is not None:
                events.append(event)
        file_state["offset"] = handle.tell()
        file_state["inode"] = current_inode
    return events, state


def _parse_iso_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _serialize_active_ip_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "ip": entry["ip"],
        "first_seen_at": entry["first_seen_at"].isoformat(),
        "last_seen_at": entry["last_seen_at"].isoformat(),
        "whitelisted": bool(entry.get("whitelisted")),
    }


def _normalize_active_ip_entry(raw: dict[str, Any]) -> dict[str, Any] | None:
    ip = str(raw.get("ip") or raw.get("active_ip") or "").strip()
    if not is_enforceable_ip(ip):
        return None
    first_seen_at = _parse_iso_datetime(raw.get("first_seen_at")) or _parse_iso_datetime(raw.get("last_seen_at"))
    last_seen_at = _parse_iso_datetime(raw.get("last_seen_at")) or first_seen_at
    if first_seen_at is None or last_seen_at is None:
        return None
    if first_seen_at > last_seen_at:
        first_seen_at = last_seen_at
    return {
        "ip": ip,
        "first_seen_at": first_seen_at,
        "last_seen_at": last_seen_at,
        "whitelisted": bool(raw.get("whitelisted")),
    }


def _sort_active_ips(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        entries,
        key=lambda item: (
            item["first_seen_at"],
            item["last_seen_at"],
            item["ip"],
        ),
    )


def _trim_active_ips(entries: list[dict[str, Any]], *, cutoff: datetime) -> list[dict[str, Any]]:
    return _sort_active_ips([entry for entry in entries if entry["last_seen_at"] >= cutoff and is_enforceable_ip(entry["ip"])])


def _upsert_active_ip(
    entries: list[dict[str, Any]],
    *,
    ip: str,
    occurred_at: datetime,
    whitelisted: bool,
) -> list[dict[str, Any]]:
    updated = False
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        if entry["ip"] != ip:
            normalized.append(entry)
            continue
        normalized.append(
            {
                "ip": ip,
                "first_seen_at": min(entry["first_seen_at"], occurred_at),
                "last_seen_at": max(entry["last_seen_at"], occurred_at),
                "whitelisted": bool(entry.get("whitelisted")) or whitelisted,
            }
        )
        updated = True
    if not updated:
        normalized.append(
            {
                "ip": ip,
                "first_seen_at": occurred_at,
                "last_seen_at": occurred_at,
                "whitelisted": whitelisted,
            }
        )
    return _sort_active_ips(normalized)


def _normalize_lease(lease: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(lease or {})
    active_ips: list[dict[str, Any]] = []
    raw_active_ips = normalized.get("active_ips")
    if isinstance(raw_active_ips, list):
        for item in raw_active_ips:
            if not isinstance(item, dict):
                continue
            normalized_item = _normalize_active_ip_entry(item)
            if normalized_item is not None:
                active_ips.append(normalized_item)
    else:
        legacy_ip = str(normalized.get("active_ip") or "").strip()
        legacy_last_seen = _parse_iso_datetime(normalized.get("last_seen_at"))
        if legacy_last_seen is not None and is_enforceable_ip(legacy_ip):
            active_ips.append(
                {
                    "ip": legacy_ip,
                    "first_seen_at": legacy_last_seen,
                    "last_seen_at": legacy_last_seen,
                    "whitelisted": False,
                }
            )
    active_ips = _sort_active_ips(active_ips)
    return {
        "active_ips": active_ips,
        "last_violation_at": _parse_iso_datetime(normalized.get("last_violation_at")),
        "last_overflow_ip": str(normalized.get("last_overflow_ip") or "").strip() or None,
        "soft_limit_hit": bool(normalized.get("soft_limit_hit")),
    }


def _serialize_lease(
    active_ips: list[dict[str, Any]],
    *,
    last_violation_at: datetime | None,
    last_overflow_ip: str | None,
    soft_limit_hit: bool,
) -> dict[str, Any]:
    normalized_active_ips = _sort_active_ips(active_ips)
    if not normalized_active_ips:
        return {}
    latest_seen = max(normalized_active_ips, key=lambda item: item["last_seen_at"])
    primary_ip = normalized_active_ips[0]["ip"]
    whitelisted_ips = [item["ip"] for item in normalized_active_ips if item.get("whitelisted")]
    counted_ips = [item["ip"] for item in normalized_active_ips if not item.get("whitelisted")]
    payload: dict[str, Any] = {
        "active_ip": primary_ip,
        "last_seen_at": latest_seen["last_seen_at"].isoformat(),
        "active_ips": [_serialize_active_ip_entry(item) for item in normalized_active_ips],
        "active_ip_count": len(counted_ips),
        "allowed_ip_count": len(normalized_active_ips),
        "whitelisted_ips": whitelisted_ips,
    }
    if last_violation_at is not None:
        payload["last_violation_at"] = last_violation_at.isoformat()
    if is_enforceable_ip(str(last_overflow_ip or "").strip()):
        payload["last_overflow_ip"] = str(last_overflow_ip).strip()
    if soft_limit_hit and last_violation_at is not None:
        payload["soft_limit_hit"] = True
    return payload


def load_whitelist_map(path: Path | None) -> dict[str, tuple[str, ...]]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(payload, dict):
        return {}

    whitelist: dict[str, tuple[str, ...]] = {}
    for email, raw_ips in payload.items():
        normalized_email = str(email or "").strip()
        if not normalized_email:
            continue
        if isinstance(raw_ips, (list, tuple, set)):
            candidates = list(raw_ips)
        else:
            candidates = [raw_ips]
        ips: list[str] = []
        for item in candidates:
            value = str(item or "").strip()
            if not is_enforceable_ip(value):
                continue
            if value not in ips:
                ips.append(value)
        if ips:
            whitelist[normalized_email] = tuple(ips)
    return whitelist


def update_leases(
    leases: dict[str, Any],
    events: list[AccessEvent],
    *,
    now: datetime,
    managed_prefixes: tuple[str, ...],
    ignored_prefixes: tuple[str, ...],
    ignored_emails: tuple[str, ...],
    lease_seconds: int,
    max_devices: int = 1,
    whitelist_by_email: dict[str, tuple[str, ...]] | None = None,
    soft_limit_enabled: bool = True,
) -> dict[str, Any]:
    payload = json.loads(json.dumps(leases or {}))
    lease_window = timedelta(seconds=max(int(lease_seconds), 1))
    whitelist_by_email = dict(whitelist_by_email or {})
    global_whitelist = set(whitelist_by_email.get("*", ()))
    enforced_max_devices = max(int(max_devices), 1)

    for event in sorted(events, key=lambda item: item.occurred_at):
        if not is_enforceable_ip(event.ip):
            continue
        if not is_managed_email(
            event.email,
            managed_prefixes=managed_prefixes,
            ignored_prefixes=ignored_prefixes,
            ignored_emails=ignored_emails,
        ):
            continue

        current = _normalize_lease(payload.get(event.email) or {})
        current_active_ips = _trim_active_ips(
            current["active_ips"],
            cutoff=event.occurred_at - lease_window,
        )
        email_whitelist = set(whitelist_by_email.get(event.email, ()))
        allowed_extra_ips = global_whitelist | email_whitelist

        if event.ip in allowed_extra_ips:
            current_active_ips = _upsert_active_ip(
                current_active_ips,
                ip=event.ip,
                occurred_at=event.occurred_at,
                whitelisted=True,
            )
        elif any(entry["ip"] == event.ip for entry in current_active_ips):
            current_active_ips = _upsert_active_ip(
                current_active_ips,
                ip=event.ip,
                occurred_at=event.occurred_at,
                whitelisted=False,
            )
        else:
            counted_active_ips = [entry for entry in current_active_ips if not entry.get("whitelisted")]
            if len(counted_active_ips) < enforced_max_devices:
                current_active_ips = _upsert_active_ip(
                    current_active_ips,
                    ip=event.ip,
                    occurred_at=event.occurred_at,
                    whitelisted=False,
                )
            else:
                current["last_violation_at"] = event.occurred_at
                current["last_overflow_ip"] = event.ip
                current["soft_limit_hit"] = bool(soft_limit_enabled)

        serialized = _serialize_lease(
            current_active_ips,
            last_violation_at=current["last_violation_at"],
            last_overflow_ip=current["last_overflow_ip"],
            soft_limit_hit=current["soft_limit_hit"],
        )
        if serialized:
            payload[event.email] = serialized
        else:
            payload.pop(event.email, None)

    cutoff = now - lease_window
    trimmed: dict[str, Any] = {}
    for email, raw in payload.items():
        lease = _normalize_lease(raw)
        current_active_ips = _trim_active_ips(lease["active_ips"], cutoff=cutoff)
        serialized = _serialize_lease(
            current_active_ips,
            last_violation_at=lease["last_violation_at"],
            last_overflow_ip=lease["last_overflow_ip"],
            soft_limit_hit=lease["soft_limit_hit"],
        )
        if serialized:
            trimmed[email] = serialized
    return trimmed


def _is_generated_rule(rule: dict[str, Any], *, managed_prefixes: tuple[str, ...]) -> bool:
    users = rule.get("user")
    if not isinstance(users, list) or not users:
        return False
    if not all(isinstance(item, str) and any(item.startswith(prefix) for prefix in managed_prefixes) for item in users):
        return False
    outbound_tag = str(rule.get("outboundTag") or "")
    if outbound_tag not in {"direct", "block"}:
        return False
    source_ips = rule.get("sourceIP")
    if outbound_tag == "direct":
        return isinstance(source_ips, list) and len(source_ips) >= 1
    return source_ips in (None, [])


def build_managed_routing_rules(active_leases: dict[str, Any]) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for email in sorted(active_leases.keys()):
        lease = _normalize_lease(active_leases[email] or {})
        allowed_ips = [entry["ip"] for entry in lease["active_ips"] if is_enforceable_ip(entry["ip"])]
        if not allowed_ips:
            continue
        rules.append(
            {
                "type": "field",
                "user": [email],
                "sourceIP": allowed_ips,
                "outboundTag": "direct",
            }
        )
        rules.append(
            {
                "type": "field",
                "user": [email],
                "outboundTag": "block",
            }
        )
    return rules


def apply_routing_rules(
    config_payload: dict[str, Any],
    active_leases: dict[str, Any],
    *,
    managed_prefixes: tuple[str, ...],
) -> tuple[dict[str, Any], bool]:
    payload = json.loads(json.dumps(config_payload))
    routing = payload.setdefault("routing", {})
    current_rules = list(routing.get("rules") or [])
    base_rules = [rule for rule in current_rules if not _is_generated_rule(rule, managed_prefixes=managed_prefixes)]
    generated_rules = build_managed_routing_rules(active_leases)
    updated_rules = generated_rules + base_rules
    changed = updated_rules != current_rules
    routing["rules"] = updated_rules
    payload["routing"] = routing
    return payload, changed


def ensure_access_log_config(config_payload: dict[str, Any], *, access_log_path: str, error_log_path: str) -> tuple[dict[str, Any], bool]:
    payload = json.loads(json.dumps(config_payload))
    log_config = dict(payload.get("log") or {})
    updated = False
    if log_config.get("access") != access_log_path:
        log_config["access"] = access_log_path
        updated = True
    if log_config.get("error") != error_log_path:
        log_config["error"] = error_log_path
        updated = True
    if log_config.get("loglevel") != "warning":
        log_config["loglevel"] = "warning"
        updated = True
    payload["log"] = log_config
    return payload, updated


def ensure_proxy_protocol_config(config_payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    payload = json.loads(json.dumps(config_payload))
    updated = False
    for inbound in payload.get("inbounds", []):
        settings = inbound.get("settings") or {}
        fallbacks = settings.get("fallbacks")
        if isinstance(fallbacks, list):
            for fallback in fallbacks:
                if int(fallback.get("xver") or 0) != 1:
                    fallback["xver"] = 1
                    updated = True
            settings["fallbacks"] = fallbacks
            inbound["settings"] = settings

        stream_settings = inbound.get("streamSettings") or {}
        if str(stream_settings.get("network") or "").strip().lower() != "xhttp":
            continue
        xhttp_settings = dict(stream_settings.get("xhttpSettings") or {})
        if xhttp_settings.get("acceptProxyProtocol") is not True:
            xhttp_settings["acceptProxyProtocol"] = True
            updated = True
        stream_settings["xhttpSettings"] = xhttp_settings
        inbound["streamSettings"] = stream_settings
    return payload, updated


def save_xray_config(config_path: Path, config_payload: dict[str, Any]) -> None:
    tmp_path = config_path.with_name(config_path.stem + ".tmp.json")
    tmp_path.write_text(json.dumps(config_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    subprocess.run(["xray", "run", "-test", "-config", str(tmp_path)], check=True)
    os.replace(tmp_path, config_path)
    subprocess.run(["systemctl", "restart", "xray"], check=True)
    subprocess.run(["systemctl", "is-active", "xray"], check=True, stdout=subprocess.DEVNULL)


def run_once(args: argparse.Namespace) -> dict[str, Any]:
    now = utcnow()
    state_path = Path(args.state)
    config_path = Path(args.config)
    access_log_path = Path(args.access_log)
    error_log_path = Path(args.error_log)
    managed_prefixes = tuple(item.strip() for item in args.managed_prefixes.split(",") if item.strip())
    ignored_prefixes = tuple(item.strip() for item in args.ignored_prefixes.split(",") if item.strip())
    ignored_emails = tuple(item.strip() for item in args.ignored_emails.split(",") if item.strip())
    whitelist_by_email = load_whitelist_map(Path(args.whitelist_file)) if args.whitelist_file else {}

    state = _load_json(state_path, default={"file": {}, "leases": {}})
    events, state = _read_access_events(access_log_path, state, first_run_bytes=args.first_run_bytes)
    active_leases = update_leases(
        state.get("leases") or {},
        events,
        now=now,
        managed_prefixes=managed_prefixes,
        ignored_prefixes=ignored_prefixes,
        ignored_emails=ignored_emails,
        lease_seconds=args.lease_seconds,
        max_devices=args.max_devices,
        whitelist_by_email=whitelist_by_email,
        soft_limit_enabled=args.soft_limit_warnings,
    )
    state["leases"] = active_leases

    config_payload = json.loads(config_path.read_text(encoding="utf-8"))
    config_payload, log_changed = ensure_access_log_config(
        config_payload,
        access_log_path=str(access_log_path),
        error_log_path=str(error_log_path),
    )
    proxy_protocol_changed = False
    if args.enable_proxy_protocol:
        config_payload, proxy_protocol_changed = ensure_proxy_protocol_config(config_payload)
    config_payload, rules_changed = apply_routing_rules(
        config_payload,
        active_leases,
        managed_prefixes=managed_prefixes,
    )
    changed = log_changed or proxy_protocol_changed or rules_changed
    if changed and not args.dry_run:
        access_log_path.parent.mkdir(parents=True, exist_ok=True)
        error_log_path.parent.mkdir(parents=True, exist_ok=True)
        save_xray_config(config_path, config_payload)
    if not args.dry_run:
        _write_json(state_path, state)

    violations = sum(1 for lease in active_leases.values() if (lease or {}).get("last_violation_at"))
    return {
        "processed_events": len(events),
        "active_leases": len(active_leases),
        "violations": violations,
        "rules_changed": rules_changed,
        "log_changed": log_changed,
        "proxy_protocol_changed": proxy_protocol_changed,
        "config_reloaded": bool(changed and not args.dry_run),
        "managed_prefixes": list(managed_prefixes),
        "max_devices": max(int(args.max_devices), 1),
        "whitelist_entries": len([key for key in whitelist_by_email.keys() if key != "*"]),
        "soft_limit_warnings": bool(args.soft_limit_warnings),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Enforce a configurable active public IP limit per Xray client email.")
    parser.add_argument("--config", default="/usr/local/etc/xray/config.json")
    parser.add_argument("--state", default="/usr/local/etc/xray/amonora_dk_single_ip_state.json")
    parser.add_argument("--access-log", default="/var/log/xray/access.log")
    parser.add_argument("--error-log", default="/var/log/xray/error.log")
    parser.add_argument("--lease-seconds", type=int, default=180)
    parser.add_argument("--max-devices", type=int, default=1)
    parser.add_argument("--first-run-bytes", type=int, default=1_000_000)
    parser.add_argument("--managed-prefixes", default=",".join(DEFAULT_MANAGED_PREFIXES))
    parser.add_argument("--ignored-prefixes", default=",".join(DEFAULT_IGNORED_PREFIXES))
    parser.add_argument("--ignored-emails", default=",".join(DEFAULT_IGNORED_EMAILS))
    parser.add_argument("--whitelist-file", default="/usr/local/etc/xray/amonora_dk_ip_whitelist.json")
    parser.add_argument("--soft-limit-warnings", dest="soft_limit_warnings", action="store_true")
    parser.add_argument("--no-soft-limit-warnings", dest="soft_limit_warnings", action="store_false")
    parser.add_argument("--enable-proxy-protocol", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.set_defaults(soft_limit_warnings=True)
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    summary = run_once(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
