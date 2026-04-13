from __future__ import annotations

import json
import logging

from collections import Counter
from dataclasses import asdict, dataclass

from sqlalchemy import select

from backend.core.database import async_session
from backend.core.models import User, VpnClient
from bot.utils.access import get_access_expires_at_from_user
from bot.utils.regions import normalize_country_code
from bot.vpn_api import XUIClient
from bot.vpn_provisioning import get_vless_provisioner


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeviceLimitEnforcementResult:
    device_id: int
    user_id: int
    protocol: str
    provider_type: str
    country_code: str | None
    status: str
    reason: str | None = None


def _device_metadata(device: VpnClient) -> dict:
    try:
        return json.loads(device.client_data or "{}")
    except json.JSONDecodeError:
        return {}


def _resolved_provider_type(device: VpnClient, metadata: dict) -> str:
    if device.protocol == "trojan":
        return "xui"
    return str(metadata.get("provider_type") or "xui").strip().lower() or "xui"


def _build_result(
    device: VpnClient,
    *,
    provider_type: str,
    country_code: str | None,
    status: str,
    reason: str | None = None,
) -> DeviceLimitEnforcementResult:
    return DeviceLimitEnforcementResult(
        device_id=int(device.id),
        user_id=int(device.user_id),
        protocol=str(device.protocol or ""),
        provider_type=provider_type,
        country_code=country_code,
        status=status,
        reason=reason,
    )


async def enforce_single_ip_limit_for_device(
    device: VpnClient,
    *,
    user: User | None = None,
) -> DeviceLimitEnforcementResult:
    metadata = _device_metadata(device)
    provider_type = _resolved_provider_type(device, metadata)
    country_code = normalize_country_code(metadata.get("country_code"))
    access_expires_at = get_access_expires_at_from_user(user) if user is not None else None
    client_uuid = device.xui_client_id or device.client_uuid

    if device.protocol not in {"vless", "trojan"}:
        return _build_result(
            device,
            provider_type=provider_type,
            country_code=country_code,
            status="skipped",
            reason="unsupported_protocol",
        )

    if not country_code:
        return _build_result(
            device,
            provider_type=provider_type,
            country_code=country_code,
            status="skipped",
            reason="missing_country_code",
        )

    if device.protocol == "vless" and provider_type != "xui":
        return _build_result(
            device,
            provider_type=provider_type,
            country_code=country_code,
            status="skipped",
            reason="provider_without_single_ip_limit",
        )

    try:
        if device.protocol == "vless":
            provisioner = get_vless_provisioner(country_code, provider_type)
            try:
                if not await provisioner.health_check():
                    return _build_result(
                        device,
                        provider_type=provider_type,
                        country_code=country_code,
                        status="failed",
                        reason="provider_healthcheck_failed",
                    )
                await provisioner.sync_vless_client(
                    client_uuid=client_uuid,
                    email=device.email,
                    metadata=metadata,
                    access_expires_at=access_expires_at,
                )
            finally:
                await provisioner.close()
            return _build_result(
                device,
                provider_type=provider_type,
                country_code=country_code,
                status="success",
            )

        xui = XUIClient(country_code=country_code)
        try:
            if not await xui.login():
                return _build_result(
                    device,
                    provider_type=provider_type,
                    country_code=country_code,
                    status="failed",
                    reason="xui_login_failed",
                )
            await xui.sync_trojan_client_expiry(
                inbound_id=int(metadata.get("inbound_id") or 0),
                client_uuid=client_uuid,
                email=device.email,
                access_expires_at=access_expires_at,
            )
        finally:
            await xui.close()
        return _build_result(
            device,
            provider_type=provider_type,
            country_code=country_code,
            status="success",
        )
    except Exception as exc:
        logger.warning(
            "Failed to backfill single-IP limit for device_id=%s user_id=%s",
            device.id,
            device.user_id,
            exc_info=True,
        )
        return _build_result(
            device,
            provider_type=provider_type,
            country_code=country_code,
            status="failed",
            reason=str(exc),
        )


async def backfill_single_ip_limits(
    *,
    user_id: int | None = None,
    limit: int | None = None,
) -> dict:
    async with async_session() as session:
        user_query = select(User)
        if user_id is not None:
            user_query = user_query.where(User.id == int(user_id))
        users = list((await session.execute(user_query)).scalars().all())

        device_query = select(VpnClient).order_by(VpnClient.id.asc())
        if user_id is not None:
            device_query = device_query.where(VpnClient.user_id == int(user_id))
        if limit is not None and int(limit) > 0:
            device_query = device_query.limit(int(limit))
        devices = list((await session.execute(device_query)).scalars().all())

    users_by_id = {user.id: user for user in users}
    results = [
        await enforce_single_ip_limit_for_device(device, user=users_by_id.get(device.user_id))
        for device in devices
    ]
    status_counts = Counter(item.status for item in results)
    reason_counts = Counter(item.reason for item in results if item.reason)

    return {
        "summary": {
            "total_devices": len(devices),
            "success": int(status_counts.get("success", 0)),
            "failed": int(status_counts.get("failed", 0)),
            "skipped": int(status_counts.get("skipped", 0)),
            "reasons": dict(sorted(reason_counts.items())),
        },
        "results": [asdict(item) for item in results],
    }
