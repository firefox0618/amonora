from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select

from backend.core.database import async_session
from backend.core.models import User, VpnClient
from bot.db import delete_vpn_client_and_return, update_vpn_client_metadata
from bot.utils.access import get_access_expires_at_from_user, has_active_access_from_user
from bot.utils.regions import (
    build_region_snapshot,
    get_country_panel_url,
    get_country_provider_type,
    is_retired_region,
    normalize_country_code,
)
from bot.vpn_api import XUIClient
from bot.vpn_provisioning import XrayCoreProvisioner
from control_bot.dispatcher import create_control_event


ACTIVE_XUI_REGION_CODES = ("de", "fr")
ACTIVE_XRAY_REGION_CODES = ("dk",)
RETIRED_REGION_CODES = ("ee",)
ACTIVE_REGION_CODES = ACTIVE_XUI_REGION_CODES + ACTIVE_XRAY_REGION_CODES
SAFE_MANAGED_REMOTE_PREFIXES = (
    "device_",
    "dashboard_",
    "bridge_",
    "test_",
    "region_probe_",
    "owner_",
    "admin_",
)


def _device_metadata(vpn_client: VpnClient) -> dict:
    if not vpn_client.client_data:
        return {}
    try:
        payload = json.loads(vpn_client.client_data)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _metadata_country(metadata: dict) -> str | None:
    raw_value = str(metadata.get("country_code") or "").strip()
    if not raw_value:
        return None
    return normalize_country_code(raw_value)


def _metadata_provider(metadata: dict, country_code: str | None) -> str:
    explicit = str(metadata.get("provider_type") or "").strip().lower()
    if explicit:
        return explicit
    return get_country_provider_type(country_code)


def _email_stem(email: str | None) -> str:
    raw = str(email or "").strip().lower()
    if not raw:
        return ""
    return raw.split("@", 1)[0]


def _is_managed_remote_email(email: str | None) -> bool:
    stem = _email_stem(email)
    return any(stem.startswith(prefix) for prefix in SAFE_MANAGED_REMOTE_PREFIXES)


def _remote_entry_key(entry: dict) -> tuple[str, str, str, str]:
    return (
        str(entry.get("country_code") or "").strip().lower(),
        str(entry.get("protocol") or "").strip().lower(),
        str(entry.get("email") or "").strip().lower(),
        str(entry.get("client_uuid") or "").strip().lower(),
    )


def _extract_panel_inventory(payload: dict, *, country_code: str) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    by_email: dict[str, dict[str, object]] = {}
    by_uuid: dict[str, dict[str, object]] = {}
    for inbound in payload.get("obj", []):
        protocol = str(inbound.get("protocol") or "").strip().lower()
        if protocol not in {"vless", "trojan"}:
            continue
        try:
            settings = json.loads(inbound.get("settings") or "{}")
        except json.JSONDecodeError:
            settings = {}
        for item in settings.get("clients", []) or []:
            email = str(item.get("email") or "").strip()
            client_uuid = str((item.get("id") if protocol == "vless" else item.get("password")) or "").strip()
            entry = {
                "country_code": country_code,
                "protocol": protocol,
                "inbound_id": int(inbound.get("id") or 0) or None,
                "email": email,
                "client_uuid": client_uuid,
                "enabled": bool(item.get("enable", True)),
                "expiry_time_ms": int(item.get("expiryTime") or 0) or 0,
                "managed": _is_managed_remote_email(email),
            }
            entries.append(entry)
            if email:
                by_email[email] = entry
            if client_uuid:
                by_uuid[client_uuid] = entry
    return {
        "entries": entries,
        "by_email": by_email,
        "by_uuid": by_uuid,
    }


async def _panel_inventory(country_code: str) -> dict[str, object]:
    client = XUIClient(country_code=country_code)
    try:
        login_ok = await client.login()
        if not login_ok:
            raise RuntimeError(f"3x-ui login failed for {country_code}")
        payload = await client.get_inbounds()
        return _extract_panel_inventory(payload, country_code=country_code)
    finally:
        await client.close()


async def _panel_login(country_code: str) -> bool:
    client = XUIClient(country_code=country_code)
    try:
        return await client.login()
    finally:
        await client.close()


async def _xray_inventory(country_code: str = "dk") -> dict[str, object]:
    provisioner = XrayCoreProvisioner(country_code)
    state = await provisioner._load_state()
    inbound = provisioner._find_client_inbound(state["config"])
    settings = inbound.get("settings") or {}
    clients = list(settings.get("clients") or [])
    entries: list[dict[str, object]] = []
    by_email: dict[str, dict[str, object]] = {}
    by_uuid: dict[str, dict[str, object]] = {}
    for item in clients:
        email = str(item.get("email") or "").strip()
        client_uuid = str(item.get("id") or "").strip()
        entry = {
            "country_code": country_code,
            "protocol": "vless",
            "email": email,
            "client_uuid": client_uuid,
            "managed": _is_managed_remote_email(email),
        }
        entries.append(entry)
        if email:
            by_email[email] = entry
        if client_uuid:
            by_uuid[client_uuid] = entry
    return {
        "entries": entries,
        "by_email": by_email,
        "by_uuid": by_uuid,
    }


def _actual_remote_entry(
    vpn_client: VpnClient,
    inventory: dict[str, object],
) -> dict[str, object] | None:
    by_email = inventory.get("by_email") or {}
    by_uuid = inventory.get("by_uuid") or {}
    identifiers = [
        str(getattr(vpn_client, "email", "") or "").strip(),
        str(getattr(vpn_client, "client_uuid", "") or "").strip(),
        str(getattr(vpn_client, "xui_client_id", "") or "").strip(),
    ]
    for identifier in identifiers:
        if not identifier:
            continue
        match = by_email.get(identifier) or by_uuid.get(identifier)
        if match is not None:
            return match
    return None


def _canonical_metadata(
    metadata: dict,
    *,
    country_code: str,
    remote_entry: dict[str, object] | None = None,
) -> dict:
    payload = dict(metadata)
    payload.update(build_region_snapshot(country_code))
    if remote_entry is not None and remote_entry.get("inbound_id") is not None:
        payload["inbound_id"] = int(remote_entry["inbound_id"])
    return payload


def _metadata_changes(before: dict, after: dict) -> dict[str, dict[str, object]]:
    changes: dict[str, dict[str, object]] = {}
    for key, value in after.items():
        if before.get(key) != value:
            changes[key] = {"before": before.get(key), "after": value}
    return changes


def _expiry_mismatch(remote_entry: dict[str, object] | None, access_expires_at: datetime | None) -> bool:
    if remote_entry is None:
        return False
    remote_expiry_ms = int(remote_entry.get("expiry_time_ms") or 0)
    if access_expires_at is None:
        return remote_expiry_ms > 0 and bool(remote_entry.get("enabled", True))
    if remote_expiry_ms <= 0:
        return True
    remote_expiry = datetime.utcfromtimestamp(remote_expiry_ms / 1000)
    return abs((remote_expiry - access_expires_at).total_seconds()) > 300


async def _repair_missing_panel_client(
    vpn_client: VpnClient,
    *,
    metadata: dict,
    user: User | None,
) -> dict:
    target_country = _metadata_country(metadata)
    if target_country not in ACTIVE_XUI_REGION_CODES:
        return {"repaired": False, "reason": "non_panel_runtime"}
    if user is None:
        return {"repaired": False, "reason": "missing_user"}
    if getattr(user, "is_blocked", False) or not has_active_access_from_user(user):
        return {"repaired": False, "reason": "inactive_access"}
    access_expires_at = get_access_expires_at_from_user(user)
    if access_expires_at is None:
        return {"repaired": False, "reason": "missing_access_expiry"}

    xui_client = XUIClient(country_code=target_country)
    try:
        if not await xui_client.login():
            raise RuntimeError(f"3x-ui login failed for {target_country}")
        protocol = str(vpn_client.protocol or "").strip().lower()
        if protocol == "trojan":
            result = await xui_client.sync_trojan_client_expiry(
                inbound_id=int(metadata.get("inbound_id") or 0),
                client_uuid=str(vpn_client.client_uuid or vpn_client.xui_client_id or ""),
                email=str(vpn_client.email or ""),
                access_expires_at=access_expires_at,
            )
        else:
            result = await xui_client.sync_vless_client_expiry(
                inbound_id=int(metadata.get("inbound_id") or 0),
                client_uuid=str(vpn_client.client_uuid or vpn_client.xui_client_id or ""),
                email=str(vpn_client.email or ""),
                access_expires_at=access_expires_at,
            )
    finally:
        await xui_client.close()

    updated_metadata = _canonical_metadata(metadata, country_code=target_country)
    if result.get("inbound_id") is not None:
        updated_metadata["inbound_id"] = int(result["inbound_id"])
    await update_vpn_client_metadata(int(vpn_client.id), updated_metadata)
    return {
        "repaired": True,
        "country_code": target_country,
        "inbound_id": updated_metadata.get("inbound_id"),
        "recreated": bool(result.get("recreated")),
    }


async def _sync_existing_panel_client(
    vpn_client: VpnClient,
    *,
    metadata: dict,
    access_expires_at: datetime | None,
) -> dict:
    target_country = _metadata_country(metadata)
    if target_country not in ACTIVE_XUI_REGION_CODES:
        return {"synced": False, "reason": "non_panel_runtime"}

    xui_client = XUIClient(country_code=target_country)
    try:
        if not await xui_client.login():
            raise RuntimeError(f"3x-ui login failed for {target_country}")
        protocol = str(vpn_client.protocol or "").strip().lower()
        if protocol == "trojan":
            result = await xui_client.sync_trojan_client_expiry(
                inbound_id=int(metadata.get("inbound_id") or 0),
                client_uuid=str(vpn_client.client_uuid or vpn_client.xui_client_id or ""),
                email=str(vpn_client.email or ""),
                access_expires_at=access_expires_at,
            )
        else:
            result = await xui_client.sync_vless_client_expiry(
                inbound_id=int(metadata.get("inbound_id") or 0),
                client_uuid=str(vpn_client.client_uuid or vpn_client.xui_client_id or ""),
                email=str(vpn_client.email or ""),
                access_expires_at=access_expires_at,
            )
    finally:
        await xui_client.close()
    return {
        "synced": True,
        "country_code": target_country,
        "inbound_id": result.get("inbound_id"),
        "recreated": bool(result.get("recreated")),
    }


async def _delete_xui_remote(entry: dict[str, object]) -> dict[str, object]:
    country_code = str(entry.get("country_code") or "").strip().lower()
    protocol = str(entry.get("protocol") or "").strip().lower()
    client = XUIClient(country_code=country_code)
    try:
        if not await client.login():
            raise RuntimeError(f"3x-ui login failed for {country_code}")
        inbound_id = int(entry.get("inbound_id") or 0)
        client_uuid = str(entry.get("client_uuid") or "").strip()
        email = str(entry.get("email") or "").strip()
        if protocol == "trojan":
            result = await client.delete_trojan_client(inbound_id, client_uuid, email=email)
        else:
            result = await client.delete_vless_client(inbound_id, client_uuid, email=email)
    finally:
        await client.close()
    return {"deleted": bool(result.get("success")), "response": result}


async def _delete_xray_remote(entry: dict[str, object]) -> dict[str, object]:
    provisioner = XrayCoreProvisioner("dk")
    result = await provisioner.delete_vless_client(
        client_uuid=str(entry.get("client_uuid") or "").strip(),
        email=str(entry.get("email") or "").strip(),
        metadata={},
    )
    return {"deleted": bool(result.get("success", True)), "response": result}


async def _retire_ee_device(
    vpn_client: VpnClient,
    *,
    metadata: dict,
    user: User | None,
    apply_changes: bool,
) -> dict[str, object]:
    follow_up_required = bool(
        user is not None and not getattr(user, "is_blocked", False) and has_active_access_from_user(user)
    )
    remote_cleanup = "not_attempted"
    remote_cleanup_reason = None
    remote_deleted = False
    provider_type = _metadata_provider(metadata, "ee")
    if provider_type == "xui" and get_country_panel_url("ee"):
        try:
            delete_result = await _delete_xui_remote(
                {
                    "country_code": "ee",
                    "protocol": str(vpn_client.protocol or "").strip().lower(),
                    "inbound_id": metadata.get("inbound_id"),
                    "email": vpn_client.email,
                    "client_uuid": vpn_client.xui_client_id or vpn_client.client_uuid,
                }
            )
            remote_deleted = bool(delete_result.get("deleted"))
            remote_cleanup = "deleted" if remote_deleted else "attempted"
            if not remote_deleted:
                remote_cleanup_reason = "delete_failed"
        except Exception as exc:
            remote_cleanup = "unreachable"
            remote_cleanup_reason = str(exc)
    elif provider_type in {"xui", "amneziawg", "retired"}:
        remote_cleanup = "unreachable"
        remote_cleanup_reason = "retired_region_no_runtime_cleanup_path"

    if not apply_changes:
        return {
            "result": "checked",
            "issues": ["retired_region_cleanup"],
            "follow_up_required": follow_up_required,
            "remote_cleanup": remote_cleanup,
            "remote_cleanup_reason": remote_cleanup_reason,
        }

    deleted = await delete_vpn_client_and_return(int(vpn_client.id))
    if deleted is None:
        return {
            "result": "manual_required",
            "issues": ["retired_region_cleanup", "local_delete_failed"],
            "follow_up_required": follow_up_required,
            "remote_cleanup": remote_cleanup,
            "remote_cleanup_reason": remote_cleanup_reason,
        }

    return {
        "result": "retired_region_cleanup",
        "issues": ["retired_region_cleanup"],
        "follow_up_required": follow_up_required,
        "remote_cleanup": remote_cleanup,
        "remote_cleanup_reason": remote_cleanup_reason,
        "remote_deleted": remote_deleted,
    }


async def check_region_integrity(*, run_cross_check: bool = True) -> dict:
    del run_cross_check
    login_de = await _panel_login("de")
    dk_health = await XrayCoreProvisioner("dk").health_check()
    return {
        "active_regions": {
            "de": {
                "provider_type": "xui",
                "panel_url": get_country_panel_url("de"),
                "login_ok": login_de,
            },
            "dk": {
                "provider_type": "xray_core",
                "health_check_ok": dk_health,
            },
        },
        "retired_regions": {
            "ee": {
                "retired": True,
                "panel_url": get_country_panel_url("ee"),
            }
        },
        "cross_check": [],
        "cross_check_ok": True,
    }


async def reconcile_vpn_clients(
    *,
    apply_changes: bool = False,
    repair_missing_remote: bool = True,
    retire_ee_cleanup: bool = False,
) -> dict:
    async with async_session() as session:
        rows = list((await session.execute(select(VpnClient).order_by(VpnClient.id.asc()))).scalars().all())
        user_ids = sorted({int(row.user_id) for row in rows if getattr(row, "user_id", None) is not None})
        users = (
            {
                item.id: item
                for item in (
                    await session.execute(select(User).where(User.id.in_(user_ids)))
                ).scalars().all()
            }
            if user_ids
            else {}
        )

    xui_inventories = {country_code: await _panel_inventory(country_code) for country_code in ACTIVE_XUI_REGION_CODES}
    xray_inventories = {country_code: await _xray_inventory(country_code) for country_code in ACTIVE_XRAY_REGION_CODES}
    matched_remote_keys: set[tuple[str, str, str, str]] = set()
    results: list[dict[str, object]] = []
    retired_follow_up_users: set[int] = set()

    for vpn_client in rows:
        metadata = _device_metadata(vpn_client)
        country_code = _metadata_country(metadata)
        if country_code is None:
            provider_type = _metadata_provider(metadata, None)
            if provider_type == "xray_core":
                country_code = "dk"
            elif provider_type == "retired":
                country_code = "ee"
            else:
                country_code = "de"
        user = users.get(int(vpn_client.user_id)) if getattr(vpn_client, "user_id", None) is not None else None
        access_active = bool(user is not None and not getattr(user, "is_blocked", False) and has_active_access_from_user(user))
        access_expires_at = get_access_expires_at_from_user(user) if user is not None else None
        remote_entry = None
        inventory = None
        if country_code in ACTIVE_XUI_REGION_CODES:
            inventory = xui_inventories[country_code]
            remote_entry = _actual_remote_entry(vpn_client, inventory)
        elif country_code in ACTIVE_XRAY_REGION_CODES:
            inventory = xray_inventories[country_code]
            remote_entry = _actual_remote_entry(vpn_client, inventory)
        if remote_entry is not None:
            matched_remote_keys.add(_remote_entry_key(remote_entry))

        entry: dict[str, object] = {
            "scope": "local_device",
            "vpn_client_id": int(vpn_client.id),
            "user_id": int(vpn_client.user_id) if getattr(vpn_client, "user_id", None) is not None else None,
            "email": str(vpn_client.email or "").strip(),
            "protocol": str(vpn_client.protocol or "").strip().lower(),
            "country_code": country_code,
            "issues": [],
            "result": "checked",
        }

        if is_retired_region(country_code):
            ee_apply = apply_changes and retire_ee_cleanup
            retirement = await _retire_ee_device(
                vpn_client,
                metadata=metadata,
                user=user,
                apply_changes=ee_apply,
            )
            entry.update(retirement)
            if retirement.get("follow_up_required") and getattr(user, "id", None) is not None:
                retired_follow_up_users.add(int(user.id))
            results.append(entry)
            continue

        canonical_metadata = _canonical_metadata(metadata, country_code=country_code, remote_entry=remote_entry)
        metadata_changes = _metadata_changes(metadata, canonical_metadata)
        needs_expiry_sync = _expiry_mismatch(remote_entry, access_expires_at)

        if remote_entry is None and access_active:
            entry["issues"] = ["remote_missing"]
            if apply_changes and repair_missing_remote:
                if country_code in ACTIVE_XUI_REGION_CODES:
                    repair_result = await _repair_missing_panel_client(vpn_client, metadata=canonical_metadata, user=user)
                    if repair_result.get("repaired"):
                        entry["result"] = "remote_recreated"
                        entry["repair"] = repair_result
                    else:
                        entry["result"] = "manual_required"
                        entry["repair_blocked_reason"] = repair_result.get("reason")
                elif country_code in ACTIVE_XRAY_REGION_CODES and access_expires_at is not None:
                    provisioner = XrayCoreProvisioner(country_code)
                    await provisioner.sync_vless_client(
                        client_uuid=str(vpn_client.client_uuid or ""),
                        email=str(vpn_client.email or ""),
                        metadata=canonical_metadata,
                        access_expires_at=access_expires_at,
                    )
                    entry["result"] = "remote_recreated"
            results.append(entry)
            continue

        if remote_entry is not None and not access_active:
            entry["issues"] = ["orphan_remote"]
            if not bool(remote_entry.get("managed")):
                entry["result"] = "manual_required"
                results.append(entry)
                continue
            if apply_changes:
                if country_code in ACTIVE_XUI_REGION_CODES:
                    delete_result = await _delete_xui_remote(remote_entry)
                else:
                    delete_result = await _delete_xray_remote(remote_entry)
                entry["delete"] = delete_result
                entry["result"] = "remote_removed" if delete_result.get("deleted") else "manual_required"
            results.append(entry)
            continue

        if needs_expiry_sync:
            entry["issues"] = [*entry["issues"], "expiry_mismatch"]
        if metadata_changes:
            entry["issues"] = [*entry["issues"], "metadata_drift"]
            entry["changes"] = metadata_changes

        if apply_changes and needs_expiry_sync and remote_entry is not None:
            if country_code in ACTIVE_XUI_REGION_CODES:
                sync_result = await _sync_existing_panel_client(
                    vpn_client,
                    metadata=canonical_metadata,
                    access_expires_at=access_expires_at,
                )
                if sync_result.get("synced"):
                    entry["sync"] = sync_result
                    if sync_result.get("inbound_id") is not None:
                        canonical_metadata["inbound_id"] = int(sync_result["inbound_id"])
                    metadata_changes = _metadata_changes(metadata, canonical_metadata)
                    entry["result"] = "metadata_fixed"
            elif country_code in ACTIVE_XRAY_REGION_CODES:
                provisioner = XrayCoreProvisioner(country_code)
                await provisioner.sync_vless_client(
                    client_uuid=str(vpn_client.client_uuid or ""),
                    email=str(vpn_client.email or ""),
                    metadata=canonical_metadata,
                    access_expires_at=access_expires_at,
                )
                entry["result"] = "metadata_fixed"

        if metadata_changes and apply_changes:
            await update_vpn_client_metadata(int(vpn_client.id), canonical_metadata)
            entry["result"] = "metadata_fixed"
            entry["changes"] = metadata_changes

        results.append(entry)

    for country_code in ACTIVE_XUI_REGION_CODES:
        for remote_entry in xui_inventories[country_code]["entries"]:
            remote_key = _remote_entry_key(remote_entry)
            if remote_key in matched_remote_keys:
                continue
            orphan_entry = {
                "scope": "remote_orphan",
                "vpn_client_id": None,
                "user_id": None,
                "email": remote_entry.get("email"),
                "protocol": remote_entry.get("protocol"),
                "country_code": country_code,
                "issues": ["orphan_remote"],
                "result": "checked",
            }
            if not bool(remote_entry.get("managed")):
                orphan_entry["result"] = "manual_required"
                results.append(orphan_entry)
                continue
            if apply_changes:
                delete_result = await _delete_xui_remote(remote_entry)
                orphan_entry["delete"] = delete_result
                orphan_entry["result"] = "remote_removed" if delete_result.get("deleted") else "manual_required"
            results.append(orphan_entry)

    for country_code in ACTIVE_XRAY_REGION_CODES:
        for remote_entry in xray_inventories[country_code]["entries"]:
            remote_key = _remote_entry_key(remote_entry)
            if remote_key in matched_remote_keys:
                continue
            orphan_entry = {
                "scope": "remote_orphan",
                "vpn_client_id": None,
                "user_id": None,
                "email": remote_entry.get("email"),
                "protocol": remote_entry.get("protocol"),
                "country_code": country_code,
                "issues": ["orphan_remote"],
                "result": "checked",
            }
            if not bool(remote_entry.get("managed")):
                orphan_entry["result"] = "manual_required"
                results.append(orphan_entry)
                continue
            if apply_changes:
                delete_result = await _delete_xray_remote(remote_entry)
                orphan_entry["delete"] = delete_result
                orphan_entry["result"] = "remote_removed" if delete_result.get("deleted") else "manual_required"
            results.append(orphan_entry)

    summary: dict[str, int] = {}
    for item in results:
        result_key = str(item.get("result") or "checked")
        summary[result_key] = summary.get(result_key, 0) + 1

    ee_cleanup_applied = apply_changes and retire_ee_cleanup
    if ee_cleanup_applied:
        retired_cleanup_count = sum(1 for item in results if item.get("result") == "retired_region_cleanup")
        if retired_cleanup_count:
            follow_up_users = sorted(retired_follow_up_users)
            await create_control_event(
                category="access",
                severity="WARNING" if follow_up_users else "INFO",
                event_type="retired_ee_cleanup",
                title="Legacy EE devices retired",
                message=(
                    f"Удалено legacy EE-устройств: {retired_cleanup_count}. "
                    f"Пользователей для ручного перевыпуска: {len(follow_up_users)}."
                ),
                payload={
                    "retired_cleanup_count": retired_cleanup_count,
                    "follow_up_user_ids": follow_up_users,
                    "apply_changes": True,
                },
                dedupe_key=f"retired-ee-cleanup:{retired_cleanup_count}:{len(follow_up_users)}",
            )

    return {
        "total": len(rows),
        "results": results,
        "summary": summary,
        "changed": [item for item in results if item.get("result") == "metadata_fixed"],
        "missing": [item for item in results if "remote_missing" in list(item.get("issues") or [])],
        "repaired": [item for item in results if item.get("result") == "remote_recreated"],
        "removed": [
            item
            for item in results
            if item.get("result") in {"remote_removed", "local_removed", "retired_region_cleanup"}
        ],
        "manual_required": [item for item in results if item.get("result") == "manual_required"],
        "checked": results,
        "retired_follow_up_users": sorted(retired_follow_up_users),
        "retire_ee_cleanup_enabled": bool(retire_ee_cleanup),
    }
