import json
import logging
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import or_, select

from backend.core.database import async_session
from backend.core.models import DeviceCompensationJob
from backend.core.schema import ensure_schema
from backend.core.tracing import normalize_trace_id, reset_current_trace_id, set_current_trace_id
from bot.db import delete_vpn_client_and_return, get_vpn_client_by_id, update_vpn_client_metadata
from bot.vpn_api import XUIClient
from bot.vpn_provisioning import get_vless_provisioner
from dashboard.security import utcnow


logger = logging.getLogger(__name__)

DEVICE_COMP_ACTION_CLEANUP_CREATED = "cleanup_created_device"
DEVICE_COMP_ACTION_FINALIZE_CREATED = "finalize_created_device"
DEVICE_COMP_ACTION_RESTORE_DELETED = "restore_deleted_device"
DEVICE_COMP_STATUS_PENDING = "pending"
DEVICE_COMP_STATUS_PROCESSING = "processing"
DEVICE_COMP_STATUS_COMPLETED = "completed"
DEVICE_COMP_STATUS_FAILED = "failed"
DEVICE_COMP_MAX_ATTEMPTS = 10
DEVICE_COMP_LOCK_STALE_SECONDS = 900


def _device_snapshot_payload(
    *,
    device_id: int | None,
    user_id: int | None,
    protocol: str,
    client_uuid: str,
    email: str,
    xui_client_id: str | None,
) -> dict[str, object]:
    return {
        "id": int(device_id) if device_id is not None else None,
        "user_id": int(user_id) if user_id is not None else None,
        "protocol": str(protocol or "").strip().lower(),
        "client_uuid": str(client_uuid or "").strip(),
        "email": str(email or "").strip(),
        "xui_client_id": str(xui_client_id).strip() if xui_client_id else None,
    }


def _device_from_payload(payload: dict) -> SimpleNamespace:
    device = dict(payload.get("device") or {})
    return SimpleNamespace(
        id=device.get("id"),
        user_id=device.get("user_id"),
        protocol=device.get("protocol"),
        client_uuid=device.get("client_uuid"),
        email=device.get("email"),
        xui_client_id=device.get("xui_client_id"),
    )


def _parse_access_expires_at(raw_value) -> datetime | None:
    if not raw_value:
        return None
    if isinstance(raw_value, datetime):
        return raw_value
    try:
        parsed = datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone().replace(tzinfo=None)
    return parsed


def _job_backoff_delay(attempt_count: int) -> timedelta:
    minutes = min(max(int(attempt_count or 1), 1) * 5, 60)
    return timedelta(minutes=minutes)


async def enqueue_cleanup_created_device_job(
    *,
    device_id: int,
    user_id: int | None,
    protocol: str,
    client_uuid: str,
    email: str,
    xui_client_id: str | None,
    metadata: dict,
) -> DeviceCompensationJob:
    payload = {
        "device": _device_snapshot_payload(
            device_id=device_id,
            user_id=user_id,
            protocol=protocol,
            client_uuid=client_uuid,
            email=email,
            xui_client_id=xui_client_id,
        ),
        "metadata": dict(metadata or {}),
    }
    dedupe_key = f"{DEVICE_COMP_ACTION_CLEANUP_CREATED}:{int(device_id)}:{str(protocol or '').strip().lower()}"
    return await _enqueue_device_compensation_job(
        action=DEVICE_COMP_ACTION_CLEANUP_CREATED,
        user_id=user_id,
        vpn_client_id=device_id,
        dedupe_key=dedupe_key,
        payload=payload,
    )


async def enqueue_finalize_created_device_job(
    *,
    device_id: int,
    user_id: int | None,
    protocol: str,
    client_uuid: str,
    email: str,
    xui_client_id: str | None,
    metadata: dict,
    access_expires_at: datetime | None,
    request_id: str | None = None,
) -> DeviceCompensationJob:
    payload = {
        "device": _device_snapshot_payload(
            device_id=device_id,
            user_id=user_id,
            protocol=protocol,
            client_uuid=client_uuid,
            email=email,
            xui_client_id=xui_client_id,
        ),
        "metadata": dict(metadata or {}),
        "access_expires_at": access_expires_at.isoformat() if access_expires_at is not None else None,
        "request_id": normalize_trace_id(request_id),
    }
    dedupe_key = f"{DEVICE_COMP_ACTION_FINALIZE_CREATED}:{int(device_id)}:{str(protocol or '').strip().lower()}"
    return await _enqueue_device_compensation_job(
        action=DEVICE_COMP_ACTION_FINALIZE_CREATED,
        user_id=user_id,
        vpn_client_id=device_id,
        request_id=request_id,
        dedupe_key=dedupe_key,
        payload=payload,
    )


async def enqueue_restore_deleted_device_job(
    *,
    device,
    metadata: dict,
    access_expires_at: datetime | None,
    request_id: str | None = None,
) -> DeviceCompensationJob:
    payload = {
        "device": _device_snapshot_payload(
            device_id=getattr(device, "id", None),
            user_id=getattr(device, "user_id", None),
            protocol=getattr(device, "protocol", None),
            client_uuid=getattr(device, "client_uuid", None),
            email=getattr(device, "email", None),
            xui_client_id=getattr(device, "xui_client_id", None),
        ),
        "metadata": dict(metadata or {}),
        "access_expires_at": access_expires_at.isoformat() if access_expires_at is not None else None,
        "request_id": normalize_trace_id(request_id),
    }
    device_id = int(getattr(device, "id", 0) or 0)
    dedupe_key = f"{DEVICE_COMP_ACTION_RESTORE_DELETED}:{device_id}:{str(getattr(device, 'protocol', '') or '').strip().lower()}"
    return await _enqueue_device_compensation_job(
        action=DEVICE_COMP_ACTION_RESTORE_DELETED,
        user_id=getattr(device, "user_id", None),
        vpn_client_id=device_id or None,
        request_id=request_id,
        dedupe_key=dedupe_key,
        payload=payload,
    )


async def _enqueue_device_compensation_job(
    *,
    action: str,
    user_id: int | None,
    vpn_client_id: int | None,
    request_id: str | None = None,
    dedupe_key: str | None,
    payload: dict,
) -> DeviceCompensationJob:
    await ensure_schema()

    async with async_session() as session:
        existing = None
        if dedupe_key:
            existing = (
                await session.execute(
                    select(DeviceCompensationJob)
                    .where(
                        DeviceCompensationJob.dedupe_key == dedupe_key,
                        DeviceCompensationJob.status.in_(
                            (DEVICE_COMP_STATUS_PENDING, DEVICE_COMP_STATUS_PROCESSING)
                        ),
                    )
                    .order_by(DeviceCompensationJob.id.desc())
                )
            ).scalar_one_or_none()
        if existing is not None:
            return existing

        job = DeviceCompensationJob(
            action=action,
            status=DEVICE_COMP_STATUS_PENDING,
            user_id=int(user_id) if user_id is not None else None,
            vpn_client_id=int(vpn_client_id) if vpn_client_id is not None else None,
            request_id=normalize_trace_id(request_id),
            dedupe_key=str(dedupe_key).strip() if dedupe_key else None,
            payload_json=json.dumps(payload, ensure_ascii=False),
            next_attempt_at=utcnow(),
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job


async def process_pending_device_compensation_jobs(*, limit: int = 10) -> dict[str, int]:
    jobs = await _claim_pending_device_compensation_jobs(limit=limit)
    result = {
        "checked": len(jobs),
        "completed": 0,
        "rescheduled": 0,
        "failed": 0,
    }
    for job in jobs:
        try:
            success = await _run_device_compensation_job(job)
        except Exception as exc:
            logger.exception("Device compensation job crashed job_id=%s action=%s", job.id, job.action)
            failed_job = await _release_device_compensation_job(job.id, error_text=str(exc))
            if failed_job is not None and failed_job.status == DEVICE_COMP_STATUS_FAILED:
                result["failed"] += 1
            else:
                result["rescheduled"] += 1
            continue
        if success:
            await _complete_device_compensation_job(job.id)
            result["completed"] += 1
        else:
            failed_job = await _release_device_compensation_job(job.id, error_text="operation_failed")
            if failed_job is not None and failed_job.status == DEVICE_COMP_STATUS_FAILED:
                result["failed"] += 1
            else:
                result["rescheduled"] += 1
    return result


async def _claim_pending_device_compensation_jobs(*, limit: int) -> list[DeviceCompensationJob]:
    await ensure_schema()

    now_point = utcnow()
    stale_before = now_point - timedelta(seconds=DEVICE_COMP_LOCK_STALE_SECONDS)
    safe_limit = max(int(limit or 0), 1)

    async with async_session() as session:
        rows = list(
            (
                await session.execute(
                    select(DeviceCompensationJob)
                    .where(
                        DeviceCompensationJob.status == DEVICE_COMP_STATUS_PENDING,
                        or_(DeviceCompensationJob.next_attempt_at.is_(None), DeviceCompensationJob.next_attempt_at <= now_point),
                        or_(DeviceCompensationJob.locked_at.is_(None), DeviceCompensationJob.locked_at < stale_before),
                    )
                    .order_by(DeviceCompensationJob.created_at.asc(), DeviceCompensationJob.id.asc())
                    .limit(safe_limit)
                    .with_for_update(skip_locked=True)
                )
            ).scalars().all()
        )
        for row in rows:
            row.status = DEVICE_COMP_STATUS_PROCESSING
            row.locked_at = now_point
            row.updated_at = now_point
        await session.commit()
        return rows


async def _complete_device_compensation_job(job_id: int) -> None:
    await ensure_schema()

    async with async_session() as session:
        job = (
            await session.execute(select(DeviceCompensationJob).where(DeviceCompensationJob.id == job_id).with_for_update())
        ).scalar_one_or_none()
        if job is None:
            return
        now_point = utcnow()
        job.status = DEVICE_COMP_STATUS_COMPLETED
        job.locked_at = None
        job.completed_at = now_point
        job.updated_at = now_point
        job.last_error = None
        await session.commit()


async def _release_device_compensation_job(job_id: int, *, error_text: str) -> DeviceCompensationJob | None:
    await ensure_schema()

    async with async_session() as session:
        job = (
            await session.execute(select(DeviceCompensationJob).where(DeviceCompensationJob.id == job_id).with_for_update())
        ).scalar_one_or_none()
        if job is None:
            return None
        now_point = utcnow()
        next_attempt_count = int(getattr(job, "attempt_count", 0) or 0) + 1
        job.attempt_count = next_attempt_count
        job.last_error = str(error_text or "")[:1000] or None
        job.locked_at = None
        job.updated_at = now_point
        if next_attempt_count >= DEVICE_COMP_MAX_ATTEMPTS:
            job.status = DEVICE_COMP_STATUS_FAILED
            job.next_attempt_at = None
        else:
            job.status = DEVICE_COMP_STATUS_PENDING
            job.next_attempt_at = now_point + _job_backoff_delay(next_attempt_count)
        await session.commit()
        await session.refresh(job)
        return job


async def _run_device_compensation_job(job: DeviceCompensationJob) -> bool:
    payload = _load_job_payload(job)
    trace_token = None
    trace_id = normalize_trace_id(getattr(job, "request_id", None)) or normalize_trace_id(payload.get("request_id"))
    if trace_id:
        trace_token = set_current_trace_id(trace_id)
    try:
        if job.action == DEVICE_COMP_ACTION_CLEANUP_CREATED:
            return await _execute_cleanup_created_device_job(payload)
        if job.action == DEVICE_COMP_ACTION_FINALIZE_CREATED:
            return await _execute_finalize_created_device_job(payload)
        if job.action == DEVICE_COMP_ACTION_RESTORE_DELETED:
            return await _execute_restore_deleted_device_job(payload)
        raise ValueError(f"Unsupported device compensation action: {job.action}")
    finally:
        if trace_token is not None:
            reset_current_trace_id(trace_token)


def _load_job_payload(job: DeviceCompensationJob) -> dict:
    raw_value = getattr(job, "payload_json", None)
    if not raw_value:
        return {}
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


async def _execute_cleanup_created_device_job(payload: dict) -> bool:
    device = _device_from_payload(payload)
    metadata = dict(payload.get("metadata") or {})
    if not getattr(device, "id", None) or not getattr(device, "protocol", None) or not getattr(device, "email", None):
        return False

    remote_deleted = await _delete_remote_state_for_snapshot(device, metadata)
    if not remote_deleted:
        return False

    deleted = await delete_vpn_client_and_return(int(device.id))
    if deleted is not None:
        return True
    return await get_vpn_client_by_id(int(device.id)) is None


async def _execute_finalize_created_device_job(payload: dict) -> bool:
    device = _device_from_payload(payload)
    metadata = dict(payload.get("metadata") or {})
    access_expires_at = _parse_access_expires_at(payload.get("access_expires_at"))
    device_id = int(getattr(device, "id", 0) or 0)
    if not device_id or not getattr(device, "protocol", None) or not getattr(device, "email", None):
        return False

    existing = await get_vpn_client_by_id(device_id)
    if existing is None:
        return await _execute_cleanup_created_device_job(payload)

    merged_device = SimpleNamespace(
        id=device_id,
        user_id=getattr(existing, "user_id", None) or getattr(device, "user_id", None),
        protocol=str(getattr(existing, "protocol", None) or getattr(device, "protocol", "") or "").strip().lower(),
        client_uuid=str(getattr(existing, "client_uuid", None) or getattr(device, "client_uuid", "") or "").strip(),
        email=str(getattr(existing, "email", None) or getattr(device, "email", "") or "").strip(),
        xui_client_id=str(getattr(existing, "xui_client_id", None) or getattr(device, "xui_client_id", "") or "").strip() or None,
    )
    if not merged_device.protocol or not merged_device.client_uuid or not merged_device.email:
        return False

    try:
        await update_vpn_client_metadata(device_id, metadata)
    except Exception:
        logger.exception("Device compensation metadata finalize failed device_id=%s", device_id)
        return False

    return await _restore_remote_state_for_snapshot(merged_device, metadata, access_expires_at)


async def _execute_restore_deleted_device_job(payload: dict) -> bool:
    device = _device_from_payload(payload)
    metadata = dict(payload.get("metadata") or {})
    access_expires_at = _parse_access_expires_at(payload.get("access_expires_at"))
    if not getattr(device, "protocol", None) or not getattr(device, "client_uuid", None) or not getattr(device, "email", None):
        return False
    return await _restore_remote_state_for_snapshot(device, metadata, access_expires_at)


async def _delete_remote_state_for_snapshot(device, metadata: dict) -> bool:
    protocol = str(getattr(device, "protocol", "") or "").strip().lower()
    client_uuid = str(getattr(device, "xui_client_id", None) or getattr(device, "client_uuid", "") or "").strip()
    email = str(getattr(device, "email", "") or "").strip()
    country_code = metadata.get("country_code")
    inbound_id = int(metadata.get("inbound_id") or 0)
    provider_type = metadata.get("provider_type")
    if not protocol or not client_uuid or not email:
        return False

    try:
        if protocol == "vless":
            provisioner = get_vless_provisioner(country_code, provider_type)
            try:
                await provisioner.delete_vless_client(
                    client_uuid=client_uuid,
                    email=email,
                    metadata=metadata,
                )
                return True
            finally:
                await provisioner.close()
        if protocol == "trojan":
            xui = XUIClient(country_code=country_code)
            try:
                if not await xui.login():
                    return False
                await xui.delete_trojan_client(
                    inbound_id=inbound_id,
                    client_uuid=client_uuid,
                    email=email,
                )
                return True
            finally:
                await xui.close()
    except Exception:
        logger.exception(
            "Device compensation remote cleanup failed device_id=%s protocol=%s",
            getattr(device, "id", None),
            protocol,
        )
        return False
    return False


async def _restore_remote_state_for_snapshot(device, metadata: dict, access_expires_at: datetime | None) -> bool:
    protocol = str(getattr(device, "protocol", "") or "").strip().lower()
    client_uuid = str(getattr(device, "xui_client_id", None) or getattr(device, "client_uuid", "") or "").strip()
    email = str(getattr(device, "email", "") or "").strip()
    country_code = metadata.get("country_code")
    provider_type = metadata.get("provider_type")
    if not protocol or not client_uuid or not email:
        return False

    try:
        if protocol == "vless":
            if provider_type == "xui":
                xui = XUIClient(country_code=country_code)
                try:
                    if not await xui.login():
                        return False
                    resolved_inbound_id = await xui.resolve_client_inbound_id(
                        "vless",
                        client_uuid,
                        email,
                        metadata.get("inbound_id"),
                    )
                    if resolved_inbound_id is None:
                        inbound = await xui.find_inbound("vless", 443)
                        if inbound is None:
                            return False
                        expiry_time_ms = int(access_expires_at.timestamp() * 1000) if access_expires_at else 0
                        result = await xui.add_vless_client(
                            inbound_id=int(inbound["id"]),
                            email=email,
                            client_uuid=client_uuid,
                            expiry_time_ms=expiry_time_ms,
                        )
                        if not result.get("success"):
                            return False
                        if getattr(device, "id", None):
                            await update_vpn_client_metadata(int(device.id), {**metadata, "inbound_id": int(inbound["id"])})
                        return True
                    await xui.sync_vless_client_expiry(
                        inbound_id=resolved_inbound_id,
                        client_uuid=client_uuid,
                        email=email,
                        access_expires_at=access_expires_at,
                    )
                    if resolved_inbound_id != metadata.get("inbound_id") and getattr(device, "id", None):
                        await update_vpn_client_metadata(int(device.id), {**metadata, "inbound_id": resolved_inbound_id})
                    return True
                finally:
                    await xui.close()

            provisioner = get_vless_provisioner(country_code, provider_type)
            try:
                if not await provisioner.health_check():
                    return False
                await provisioner.sync_vless_client(
                    client_uuid=client_uuid,
                    email=email,
                    metadata=metadata,
                    access_expires_at=access_expires_at,
                )
                return True
            finally:
                await provisioner.close()

        if protocol == "trojan":
            xui = XUIClient(country_code=country_code)
            try:
                if not await xui.login():
                    return False
                resolved_inbound_id = await xui.resolve_client_inbound_id(
                    "trojan",
                    client_uuid,
                    email,
                    metadata.get("inbound_id"),
                )
                if resolved_inbound_id is not None:
                    await xui.sync_trojan_client_expiry(
                        inbound_id=resolved_inbound_id,
                        client_uuid=client_uuid,
                        email=email,
                        access_expires_at=access_expires_at,
                    )
                    if resolved_inbound_id != metadata.get("inbound_id") and getattr(device, "id", None):
                        await update_vpn_client_metadata(int(device.id), {**metadata, "inbound_id": resolved_inbound_id})
                    return True

                inbound = await xui.find_inbound("trojan", 8443)
                if inbound is None:
                    return False
                expiry_time_ms = int(access_expires_at.timestamp() * 1000) if access_expires_at else 0
                result = await xui.add_trojan_client(
                    inbound_id=int(inbound["id"]),
                    email=email,
                    password=client_uuid,
                    expiry_time_ms=expiry_time_ms,
                )
                if not result.get("success"):
                    return False
                if getattr(device, "id", None):
                    await update_vpn_client_metadata(int(device.id), {**metadata, "inbound_id": int(inbound["id"])})
                return True
            finally:
                await xui.close()
    except Exception:
        logger.exception(
            "Device compensation remote restore failed device_id=%s protocol=%s",
            getattr(device, "id", None),
            protocol,
        )
        return False
    return False
