import json
import logging
import time
from urllib.parse import quote, urlsplit, urlunsplit

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from backend.core.analytics import (
    EVENT_CONNECTION_READY,
    EVENT_CONNECTION_STARTED,
    EVENT_CONFIG_ISSUE_FAILED,
    EVENT_CONFIG_ISSUED,
    EVENT_CONFIG_REQUESTED,
    EVENT_CONNECTION_FAILED,
    safe_emit_analytics_event,
)
from backend.core.tracing import current_or_new_trace_id
from bot.device_compensation import enqueue_finalize_created_device_job
from bot.config import config
from bot.db import (
    clear_public_subscription_device_slot_binding,
    count_region_vpn_clients,
    count_user_account_devices,
    create_vpn_client,
    delete_vpn_client_and_return,
    get_active_device_slot_counts_for_users,
    get_access_expires_at,
    get_user_by_telegram_id,
    get_vpn_client_by_id,
    mark_trial_technical_engagement,
    update_vpn_client_metadata,
)
from bot.keyboards.devices import (
    add_device_keyboard,
    device_card_keyboard,
    device_credential_keyboard,
    device_country_keyboard,
    device_happ_install_keyboard,
    device_happ_question_keyboard,
    device_limit_reached_keyboard,
    device_instruction_keyboard,
    device_os_keyboard,
    device_protocol_keyboard,
    device_protocol_keyboard_for_existing,
    device_settings_keyboard,
    devices_list_keyboard,
    public_device_card_keyboard,
)
from bot.keyboards.tariffs import tariffs_keyboard
from bot.keyboards.home import blocked_home_keyboard
from control_bot.dispatcher import create_control_event
from bot.utils.modes import (
    format_mode,
    get_auto_mode,
    get_mode_connection_profile,
    get_mode_protocol,
    infer_mode_from_protocol,
    is_mode_key,
    mode_available_for_user,
    mode_supported_in_region,
    normalize_mode,
    resolve_effective_mode,
)
from bot.utils.regions import (
    build_region_snapshot,
    get_country_name,
    get_region_limit_rule,
    is_cross_region_change,
    is_retired_region,
    normalize_country_code,
    parse_load_average,
    region_soft_limit_reasons,
)
from bot.vpn_provisioning import get_vless_provisioner
from bot.utils.access import get_device_limit_for_user, has_active_access_from_user, has_active_subscription_from_user
from bot.utils.device_slots import DEFAULT_DEVICE_LIMIT, MAX_DEVICE_LIMIT, device_slot_unit_price_rub, remaining_device_slot_capacity
from bot.public_subscription import PUBLIC_SUBSCRIPTION_BINDING_METADATA_KEYS, get_account_devices_for_user
from bot.utils.qr import generate_qr_image
from bot.utils.routing import build_split_routing_pack_for_device, dumps_pack
from bot.utils.texts import (
    PANEL_CONNECTION_ERROR_TEXT,
    PANEL_OPERATION_ERROR_TEXT,
    USER_NOT_FOUND_TEXT,
    access_required_text,
    ask_device_country_text,
    ask_device_name_text,
    ask_device_os_text,
    ask_device_protocol_text,
    ask_existing_device_country_text,
    ask_existing_device_protocol_text,
    blocked_user_action_text,
    changed_country_text,
    changed_device_os_text,
    delete_device_not_found_text,
    device_delivery_retry_text,
    device_card_text,
    device_list_summary_line,
    device_region_recreate_required_text,
    device_deleted_text,
    device_guide_text,
    device_limit_reached_text,
    device_list_title,
    device_settings_text,
    devices_overview_text,
    renamed_device_text,
    mobile_mode_placeholder_text,
    split_routing_pack_text,
    trojan_delivery_text,
    vless_delivery_text,
    vless_happ_download_text,
    vless_happ_question_text,
    vpn_client_created_text,
)
from bot.utils.vless import (
    build_connection_name,
    build_trojan_link,
)
from bot.vpn_api import XUIClient
from dashboard.services import get_server_snapshots


logger = logging.getLogger(__name__)
router = Router()

MOBILE_HAPP_OS = {"android", "ios"}
MOBILE_MODE_OVERRIDE_NAME = "☁️ AMONORA-LTE"


async def _region_capacity_error(country_code: str) -> str | None:
    normalized = normalize_country_code(country_code)
    if is_retired_region(normalized):
        return "⚠️ Регион Эстония выведен из продуктового контура. Создай устройство в Германии или Дании."
    if normalized != "ee":
        return None

    rule = get_region_limit_rule(normalized)
    snapshots = await get_server_snapshots(force_refresh=True)
    snapshot = next((item for item in snapshots if item.get("country_code") == normalized), None)
    if snapshot is None:
        return "⚠️ Сервер Эстония сейчас временно недоступен. Попробуй Германию."

    if snapshot.get("status") != "active":
        return "⚠️ Сервер Эстония сейчас недоступен. Попробуй Германию."
    if snapshot.get("host_status") not in {None, "ok"} or snapshot.get("ssh_status") not in {None, "active", "ok"}:
        return "⚠️ Сервер Эстония сейчас недоступен. Попробуй Германию."
    if snapshot.get("xui_status") in {"error", "failed"}:
        return "⚠️ Сервер Эстония сейчас недоступен. Попробуй Германию."

    active_devices = await count_region_vpn_clients(normalized, active_only=True)
    reasons = region_soft_limit_reasons(
        rule,
        active_devices=active_devices,
        cpu_used_percent=float(snapshot.get("cpu_percent") or 0),
        memory_used_percent=float(snapshot.get("memory_used_percent") or 0),
        disk_used_percent=float(snapshot.get("disk_used_percent") or 0),
        load_average=parse_load_average(snapshot.get("load")),
    )

    if reasons:
        return "⚠️ В данный момент сервер Эстония перегружен. Попробуй Германию."
    if snapshot.get("overall_state") == "critical":
        return "⚠️ В данный момент сервер Эстония перегружен. Попробуй Германию."

    return None


class DeviceStates(StatesGroup):
    waiting_name = State()
    waiting_rename = State()


async def _annotate_user_device_slots(user) -> int:
    if user is None or getattr(user, "id", None) is None:
        return 0
    counts = await get_active_device_slot_counts_for_users([int(user.id)])
    active_slots = int(counts.get(int(user.id), 0))
    setattr(user, "active_device_slot_addons", active_slots)
    return active_slots


async def _device_limit_state(user, devices_count: int) -> dict:
    active_slots = await _annotate_user_device_slots(user)
    device_limit = get_device_limit_for_user(user)
    can_buy_more = (
        has_active_subscription_from_user(user)
        and device_limit <= MAX_DEVICE_LIMIT
        and remaining_device_slot_capacity(user, base_limit=DEFAULT_DEVICE_LIMIT) > 0
    )
    expires_at = getattr(user, "subscription_expires_at", None)
    return {
        "active_slots": active_slots,
        "device_limit": device_limit,
        "can_buy_more": can_buy_more,
        "expires_text": expires_at.strftime("%Y-%m-%d %H:%M:%S") if expires_at else None,
        "is_over_limit": devices_count > device_limit,
    }


async def _get_owned_device_for_telegram(telegram_id: int, device_id: int):
    user = await get_user_by_telegram_id(telegram_id)
    if user is None:
        return None, None

    device = await get_vpn_client_by_id(device_id)
    if device is None or device.user_id != user.id:
        return user, None
    return user, device


def _callback_kind_to_device_kind(raw_kind: str | None) -> str:
    normalized = str(raw_kind or "").strip().lower()
    if normalized in {"public", "public_slot", "slot"}:
        return "public_slot"
    return "legacy_device"


def _device_callback_suffix(device_kind: str | None) -> str:
    return "public" if _callback_kind_to_device_kind(device_kind) == "public_slot" else "vpn"


def _parse_device_target_callback(data: str | None, *, action: str) -> tuple[str, int] | None:
    parts = str(data or "").split(":")
    if len(parts) < 3 or parts[0] != "device":
        return None

    try:
        if parts[1] == "public" and len(parts) >= 4 and parts[2] == action:
            return "public_slot", int(parts[3])
        if parts[1] != action:
            return None
        if len(parts) == 3:
            return "legacy_device", int(parts[2])
        return _callback_kind_to_device_kind(parts[2]), int(parts[3])
    except (TypeError, ValueError):
        return None


async def _emit_credential_delivery_event(
    device,
    metadata: dict,
    *,
    reissued: bool = False,
) -> None:
    country_name = metadata.get("country_name", "Германия")
    device_name = metadata.get("device_name", device.email)
    protocol = metadata.get("protocol", device.protocol)
    if protocol in {"vless", "trojan"}:
        title = "Ключ перевыпущен" if reissued else "Ключ выдан"
        event_type = "access_key_reissued" if reissued else "access_key_issued"
        noun = "Ключ"
    else:
        title = "Конфиг перевыпущен" if reissued else "Конфиг выдан"
        event_type = "access_config_reissued" if reissued else "access_config_issued"
    await create_control_event(
        category="access",
        severity="INFO",
        event_type=event_type,
        title=title,
        message=_credential_delivery_event_message(
            user_id=device.user_id,
            device_name=device_name,
            protocol=protocol,
            country_name=country_name,
            include_country=protocol not in {"vless", "trojan"},
        ),
        entity_type="vpn_client",
        entity_id=str(device.id),
        payload={
            "user_id": device.user_id,
            "device_id": device.id,
            "device_name": device_name,
            "protocol": protocol,
            "country_code": metadata.get("country_code"),
            "reissued": reissued,
        },
        dedupe_key=f"{event_type}:{device.id}:{int(time.time())}",
        cooldown_seconds=0,
    )
    if not reissued:
        await safe_emit_analytics_event(
            event_name=EVENT_CONFIG_ISSUED,
            user_id=int(device.user_id),
            dedupe_key=f"config-issued:{int(device.id)}",
            vpn_client_id=int(device.id),
            country_code=str(metadata.get("country_code") or "").strip().lower() or None,
            payload={
                "device_name": device_name,
                "device_type": metadata.get("device_type"),
                "protocol": protocol,
                "mode": metadata.get("mode"),
                "country_name": country_name,
            },
        )


def _credential_delivery_event_message(
    *,
    user_id: int,
    device_name: str,
    protocol: str,
    country_name: str,
    include_country: bool,
) -> str:
    parts = [
        f"Пользователь: <code>{user_id}</code>",
        f"Устройство: <b>{device_name}</b>",
        f"Протокол: <b>{protocol}</b>",
    ]
    if include_country:
        parts.append(f"Страна: <b>{country_name}</b>")
    return " • ".join(parts)


async def _emit_device_country_changed_event(device, previous_country_code: str, target_country_code: str) -> None:
    await create_control_event(
        category="access",
        severity="INFO",
        event_type="device_country_changed",
        title="Смена ноды устройства",
        message=(
            f"Пользователь: <code>{device.user_id}</code>\n"
            f"Устройство: <b>{_device_metadata(device).get('device_name', device.email)}</b>\n"
            f"Было: <b>{get_country_name(previous_country_code)}</b>\n"
            f"Стало: <b>{get_country_name(target_country_code)}</b>"
        ),
        entity_type="vpn_client",
        entity_id=str(device.id),
        payload={
            "user_id": device.user_id,
            "device_id": device.id,
            "previous_country_code": previous_country_code,
            "target_country_code": target_country_code,
        },
        dedupe_key=f"device-country:{device.id}:{target_country_code}:{int(time.time())}",
        cooldown_seconds=0,
    )


async def _emit_provisioning_failure_event(
    user_id: int,
    protocol: str,
    country_code: str,
    error_text: str,
    *,
    request_id: str | None = None,
) -> None:
    await create_control_event(
        category="access",
        severity="CRITICAL",
        event_type="access_provisioning_failed",
        title="Ошибка выдачи доступа",
        message=(
            f"Пользователь: <code>{user_id}</code>\n"
            f"Протокол: <b>{protocol}</b>\n"
            f"Страна: <b>{get_country_name(country_code)}</b>\n"
            f"Причина: <b>{error_text}</b>"
        ),
        entity_type="user",
        entity_id=str(user_id),
        payload={
            "user_id": user_id,
            "protocol": protocol,
            "country_code": country_code,
            "error": error_text,
            "trace_id": request_id,
        },
        dedupe_key=f"provisioning-failed:{user_id}:{protocol}:{country_code}",
        request_id=request_id,
    )
    failure_key = f"provisioning-failed:{user_id}:{protocol}:{country_code}"
    payload = {
        "protocol": protocol,
        "country_code": country_code,
        "error": error_text,
        "trace_id": request_id,
    }
    await safe_emit_analytics_event(
        event_name=EVENT_CONFIG_ISSUE_FAILED,
        user_id=int(user_id),
        dedupe_key=failure_key,
        country_code=country_code,
        payload=payload,
    )
    await safe_emit_analytics_event(
        event_name=EVENT_CONNECTION_FAILED,
        user_id=int(user_id),
        dedupe_key=f"connection-{failure_key}",
        country_code=country_code,
        payload=payload,
    )


async def _emit_delivery_failure_event(
    user_id: int,
    device_id: int,
    protocol: str,
    country_code: str,
    error_text: str,
    *,
    request_id: str | None = None,
) -> None:
    await create_control_event(
        category="access",
        severity="WARNING",
        event_type="access_delivery_failed",
        title="Выдача инструкции прервалась",
        message=(
            f"Пользователь: <code>{user_id}</code>\n"
            f"Устройство: <b>{device_id}</b>\n"
            f"Протокол: <b>{protocol}</b>\n"
            f"Страна: <b>{get_country_name(country_code)}</b>\n"
            f"Причина: <b>{error_text}</b>"
        ),
        entity_type="vpn_client",
        entity_id=str(device_id),
        payload={
            "user_id": user_id,
            "device_id": device_id,
            "protocol": protocol,
            "country_code": country_code,
            "error": error_text,
            "trace_id": request_id,
        },
        dedupe_key=f"delivery-failed:{device_id}:{protocol}:{country_code}",
        cooldown_seconds=0,
        request_id=request_id,
    )
    failure_key = f"delivery-failed:{device_id}:{protocol}:{country_code}"
    payload = {
        "protocol": protocol,
        "country_code": country_code,
        "error": error_text,
        "device_id": int(device_id),
        "trace_id": request_id,
    }
    await safe_emit_analytics_event(
        event_name=EVENT_CONFIG_ISSUE_FAILED,
        user_id=int(user_id),
        dedupe_key=failure_key,
        vpn_client_id=int(device_id),
        country_code=country_code,
        payload=payload,
    )
    await safe_emit_analytics_event(
        event_name=EVENT_CONNECTION_FAILED,
        user_id=int(user_id),
        dedupe_key=f"connection-{failure_key}",
        vpn_client_id=int(device_id),
        country_code=country_code,
        payload=payload,
    )


async def _mark_trial_technical_engagement_safe(user_id: int) -> None:
    try:
        await mark_trial_technical_engagement(user_id)
    except Exception:
        logger.warning("Failed to mark trial technical engagement for user_id=%s", user_id, exc_info=True)


async def _cleanup_provisioned_device_after_failure(
    *,
    device_id: int,
    protocol: str,
    client_uuid: str,
    email: str,
    xui_client_id: str | None,
    metadata: dict,
) -> bool:
    country_code = metadata.get("country_code")
    remote_client_uuid = xui_client_id or client_uuid
    remote_deleted = False

    try:
        if protocol == "vless":
            provisioner = get_vless_provisioner(country_code, metadata.get("provider_type"))
            try:
                await provisioner.delete_vless_client(
                    client_uuid=remote_client_uuid,
                    email=email,
                    metadata=metadata,
                )
                remote_deleted = True
            finally:
                await provisioner.close()
        elif protocol == "trojan":
            xui_client = XUIClient(country_code=country_code)
            try:
                if not await xui_client.login():
                    return False
                await xui_client.delete_trojan_client(
                    inbound_id=int(metadata.get("inbound_id") or 0),
                    client_uuid=remote_client_uuid,
                    email=email,
                )
                remote_deleted = True
            finally:
                await xui_client.close()
        else:
            logger.warning(
                "Provisioning cleanup skipped for unsupported protocol device_id=%s protocol=%s",
                device_id,
                protocol,
            )
            return False
    except Exception:
        logger.exception(
            "Failed to cleanup remote state after provisioning failure device_id=%s protocol=%s",
            device_id,
            protocol,
        )
        return False

    try:
        deleted = await delete_vpn_client_and_return(int(device_id))
    except Exception:
        logger.exception("Failed to cleanup local device row after provisioning failure device_id=%s", device_id)
        return False
    return remote_deleted and (deleted is not None or await get_vpn_client_by_id(int(device_id)) is None)


def _device_metadata(vpn_client) -> dict:
    data = json.loads(vpn_client.client_data) if vpn_client.client_data else {}
    data.setdefault("device_name", vpn_client.email)
    data.setdefault("device_type", "other")
    data.setdefault("protocol", vpn_client.protocol)
    if not data.get("connection_uri"):
        if vpn_client.protocol == "trojan":
            data["connection_uri"] = _normalize_connection_uri(data.get("trojan_link"))
        else:
            data["connection_uri"] = _normalize_connection_uri(data.get("vless_link"))
    data.setdefault("mode", infer_mode_from_protocol(data.get("protocol"), data))
    if data.get("protocol") == "vless":
        data.setdefault("stream_network", "tcp")
        data.setdefault("transport_label", "TCP")
    data.update(build_region_snapshot(data.get("country_code")))
    return data


def _vless_transport_metadata(inbound: dict) -> dict[str, str]:
    transport = extract_vless_transport_metadata(inbound)
    return {
        "stream_network": transport["stream_network"],
        "transport_label": transport["transport_label"],
        "stream_path": transport.get("stream_path", ""),
        "stream_host": transport.get("stream_host", ""),
        "stream_mode": transport.get("stream_mode", ""),
    }


def _device_delivery_mode(protocol: str, os_type: str) -> str | None:
    if protocol not in {"vless", "trojan"}:
        return None
    if os_type in MOBILE_HAPP_OS:
        return "mobile_happ"
    return "desktop_generic"


def _protocol_delivery_name(protocol: str, metadata: dict | None = None) -> str:
    return format_mode(infer_mode_from_protocol(protocol, metadata))


def _normalize_connection_uri(value: str | None) -> str | None:
    if value is None:
        return None
    payload = str(value).strip()
    return payload or None


def _resolve_connection_uri(device, metadata: dict) -> str | None:
    payload = _normalize_connection_uri(metadata.get("connection_uri"))
    if payload:
        return payload
    if device.protocol == "trojan":
        return _normalize_connection_uri(metadata.get("trojan_link"))
    return _normalize_connection_uri(metadata.get("vless_link"))


async def _edit_or_send(message: Message, text: str, reply_markup=None) -> Message:
    try:
        return await message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return message
        return await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)


async def _edit_message_by_state(message: Message, state: FSMContext, text: str, reply_markup=None) -> None:
    data = await state.get_data()
    chat_id = data.get("screen_chat_id")
    message_id = data.get("screen_message_id")
    if chat_id and message_id:
        try:
            await message.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )
            try:
                await message.delete()
            except TelegramBadRequest:
                pass
            return
        except TelegramBadRequest:
            pass

    sent = await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    await state.update_data(screen_chat_id=sent.chat.id, screen_message_id=sent.message_id)
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


async def _show_devices_list(message: Message, user) -> None:
    if getattr(user, "is_blocked", False):
        await _edit_or_send(
            message,
            blocked_user_action_text(),
            reply_markup=blocked_home_keyboard,
        )
        return

    devices = list(await get_account_devices_for_user(int(user.id)))
    devices_count = len(devices)

    if not has_active_access_from_user(user):
        await _edit_or_send(
            message,
            access_required_text(),
            reply_markup=tariffs_keyboard(),
        )
        return

    limit_state = await _device_limit_state(user, devices_count)

    device_rows = []
    device_lines = []
    for device in devices:
        device_kind = str(device.get("kind") or "legacy_device").strip().lower()
        device_name = str(device.get("title") or device.get("device_model") or f"Устройство #{device.get('id') or '?'}").strip()
        protocol = str(device.get("protocol") or "sub").strip().lower()
        device_rows.append(
            {
                "id": int(device.get("id") or 0),
                "title": device_list_title(
                    device_name,
                    str(device.get("device_type") or "other"),
                    protocol,
                ),
                "callback_data": f"device:view:{_device_callback_suffix(device_kind)}:{int(device.get('id') or 0)}",
            }
        )
        device_lines.append(
            device_list_summary_line(
                len(device_lines) + 1,
                device_name,
                protocol,
                device,
            )
        )

    await _edit_or_send(
        message,
        devices_overview_text(
            devices_count,
            "\n\n".join(device_lines),
            device_limit=limit_state["device_limit"],
            extra_slots_active=int(getattr(user, "active_device_slot_addons", 0) or 0),
        ),
        reply_markup=devices_list_keyboard(
            device_rows,
            allow_add=devices_count < limit_state["device_limit"],
            can_buy_more=limit_state["can_buy_more"],
            price_rub=device_slot_unit_price_rub(),
        )
        if device_rows
        else add_device_keyboard(),
    )


async def _show_user_home_from_callback(callback: CallbackQuery) -> None:
    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    from bot.handlers.start import _send_home

    await _send_home(callback.message, callback.from_user.id)
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.answer()


def _public_slot_card_text(device_data: dict, expires_text: str) -> str:
    device_name = str(device_data.get("device_model") or device_data.get("title") or "Happ device").strip() or "Happ device"
    slot_index = int(device_data.get("slot_index") or device_data.get("id") or 0)
    os_name = str(device_data.get("os_name") or "Устройство").strip() or "Устройство"
    os_version = str(device_data.get("os_version") or "—").strip() or "—"
    source_label = str(device_data.get("source_label") or "Happ / единая ссылка").strip() or "Happ / единая ссылка"
    bound_at = str(device_data.get("bound_at") or "—").strip() or "—"
    return (
        f"📱 <b>{device_name}</b>\n"
        "────────────\n"
        f"🔗 Источник: <b>{source_label}</b>\n"
        f"🎛 Слот: <b>{slot_index}</b>\n"
        f"🖥 Платформа: <b>{os_name}</b>{'' if os_version == '—' else f' • {os_version}'}\n"
        f"🕒 Привязано: <b>{bound_at}</b>\n"
        f"⏳ Доступ до: <b>{expires_text}</b>\n"
        "────────────\n"
        "Это устройство использует единую ссылку подписки. Ниже можно освободить слот, если устройство больше не используется."
    )


async def _send_vless_config(message_target, device, metadata, expires_text: str) -> None:
    if _should_use_mobile_mode_override(metadata):
        mobile_override_link = _mobile_mode_override_link(metadata.get("country_code"))
        if mobile_override_link:
            connection_uri = _normalize_connection_uri(_with_connection_name(mobile_override_link, MOBILE_MODE_OVERRIDE_NAME))
            metadata["vless_link"] = connection_uri
            metadata["connection_uri"] = connection_uri
            metadata["link_delivery_source"] = "mobile_mode_override"
            await update_vpn_client_metadata(device.id, metadata)
            await _send_connection_uri_message(message_target, device, metadata, expires_text, connection_uri)
            await _mark_trial_technical_engagement_safe(device.user_id)
            return

    provisioner = get_vless_provisioner(metadata.get("country_code"), metadata.get("provider_type"))
    try:
        success = await provisioner.health_check()
        if not success:
            await message_target.answer(PANEL_CONNECTION_ERROR_TEXT, parse_mode=ParseMode.HTML)
            return
        refreshed_metadata = await provisioner.build_vless_metadata(
            client_uuid=device.client_uuid,
            email=device.email,
            country_code=metadata.get("country_code"),
            base_metadata=metadata,
        )
        connection_uri = _normalize_connection_uri(refreshed_metadata["vless_link"])
        refreshed_metadata["vless_link"] = connection_uri
        refreshed_metadata["connection_uri"] = connection_uri
        metadata.update(refreshed_metadata)
        if metadata.get("link_delivery_source") == "mobile_mode_override":
            metadata.pop("link_delivery_source", None)
        await update_vpn_client_metadata(device.id, metadata)
    finally:
        await provisioner.close()

    await _send_connection_uri_message(message_target, device, metadata, expires_text, connection_uri)
    await _mark_trial_technical_engagement_safe(device.user_id)


async def _send_trojan_config(message_target, device, metadata, expires_text: str) -> None:
    connection_name = build_connection_name(
        country_code=metadata.get("country_code"),
        country_name=metadata.get("country_name"),
        email=device.email,
    )
    trojan_link = metadata.get("trojan_link")
    if trojan_link and "#" in trojan_link:
        trojan_link = _normalize_connection_uri(f"{trojan_link.split('#', 1)[0]}#{quote(connection_name)}")
        metadata["trojan_link"] = trojan_link
        metadata["connection_uri"] = trojan_link
        await update_vpn_client_metadata(device.id, metadata)

    if not trojan_link:
        xui_client = XUIClient(country_code=metadata.get("country_code"))
        try:
            success = await xui_client.login()
            if not success:
                await message_target.answer(PANEL_CONNECTION_ERROR_TEXT, parse_mode=ParseMode.HTML)
                return
            inbound = await xui_client.find_inbound("trojan", 8443)
            if inbound is None:
                await message_target.answer(PANEL_OPERATION_ERROR_TEXT, parse_mode=ParseMode.HTML)
                return
            trojan_link = build_trojan_link(
                inbound=inbound,
                password=device.client_uuid,
                email=device.email,
                connection_name=connection_name,
                country_code=metadata.get("country_code"),
            )
            trojan_link = _normalize_connection_uri(trojan_link)
            metadata["trojan_link"] = trojan_link
            metadata["connection_uri"] = trojan_link
            await update_vpn_client_metadata(device.id, metadata)
        finally:
            await xui_client.close()

    connection_uri = _normalize_connection_uri(trojan_link)
    await _send_connection_uri_message(message_target, device, metadata, expires_text, connection_uri)
    await _mark_trial_technical_engagement_safe(device.user_id)


async def _send_device_config(message_target, device, metadata, expires_text: str) -> None:
    if device.protocol == "trojan":
        await _send_trojan_config(message_target, device, metadata, expires_text)
    else:
        await _send_vless_config(message_target, device, metadata, expires_text)


async def _send_connection_uri_message(message_target, device, metadata, expires_text: str, connection_uri: str) -> None:
    text = vpn_client_created_text(
        device_name=metadata.get("device_name", device.email),
        protocol=format_mode(infer_mode_from_protocol(device.protocol, metadata)),
        country_name=metadata.get("country_name", "Германия"),
        access_expires_at=expires_text,
        connection_uri=connection_uri,
    )
    try:
        await message_target.answer(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=device_credential_keyboard(device.id, connection_uri),
        )
    except TelegramBadRequest as exc:
        if "BUTTON_COPY_TEXT_INVALID" not in str(exc):
            raise
        logger.warning(
            "Copy-text button is invalid for device %s; retrying without copy button",
            device.id,
            exc_info=True,
        )
        await message_target.answer(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=device_credential_keyboard(device.id, connection_uri, allow_copy=False),
        )


async def _enforce_device_key_limit(device, metadata: dict, access_expires_at) -> None:
    try:
        if device.protocol == "vless":
            provider_type = metadata.get("provider_type")
            if provider_type not in {None, "xui"}:
                return
            provisioner = get_vless_provisioner(metadata.get("country_code"), provider_type)
            try:
                if not await provisioner.health_check():
                    return
                await provisioner.sync_vless_client(
                    client_uuid=device.client_uuid,
                    email=device.email,
                    metadata=metadata,
                    access_expires_at=access_expires_at,
                )
            finally:
                await provisioner.close()
            return

        if device.protocol != "trojan":
            return

        inbound_id = metadata.get("inbound_id")
        if not inbound_id:
            return

        xui_client = XUIClient(country_code=metadata.get("country_code"))
        try:
            if not await xui_client.login():
                return
            await xui_client.sync_trojan_client_expiry(
                inbound_id=inbound_id,
                client_uuid=device.client_uuid,
                email=device.email,
                access_expires_at=access_expires_at,
            )
        finally:
            await xui_client.close()
    except Exception:
        logger.warning(
            "Failed to re-apply key limit for device_id=%s protocol=%s",
            device.id,
            device.protocol,
            exc_info=True,
        )


async def _send_vless_qr(message_target, device, metadata: dict) -> None:
    payload = metadata.get("vless_link")
    if not payload:
        return

    qr_buffer = generate_qr_image(payload)
    qr_file = BufferedInputFile(qr_buffer.getvalue(), filename=f"amonora_{device.id}_vless_qr.png")
    await message_target.answer_photo(photo=qr_file)


def _mobile_mode_override_link(country_code: str | None) -> str | None:
    normalized = normalize_country_code(country_code)
    if normalized == "de":
        return config.mobile_mode_override_link_de
    if normalized == "dk":
        return config.mobile_mode_override_link_dk
    return None


def _should_use_mobile_mode_override(metadata: dict | None) -> bool:
    payload = metadata or {}
    if payload.get("delivery_mode") != "mobile_happ":
        return False
    return normalize_mode(payload.get("mode") or payload.get("resolved_mode")) == "mobile"


def _with_connection_name(link: str, connection_name: str) -> str:
    parts = urlsplit(link)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, quote(connection_name)))


async def _show_device_card(callback: CallbackQuery, device_id: int) -> None:
    user, device = await _get_owned_device_for_telegram(callback.from_user.id, device_id)
    if user is not None and getattr(user, "is_blocked", False):
        await callback.message.answer(blocked_user_action_text(), parse_mode=ParseMode.HTML, reply_markup=blocked_home_keyboard)
        await callback.answer()
        return

    if user is None:
        await callback.message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
        return

    if device is None:
        await callback.message.answer(delete_device_not_found_text(), parse_mode=ParseMode.HTML)
        return

    metadata = _device_metadata(device)
    access_expires_at = await get_access_expires_at(device.user_id)
    expires_text = access_expires_at.strftime("%Y-%m-%d %H:%M:%S") if access_expires_at else "—"

    await _edit_or_send(
        callback.message,
        device_card_text(metadata, expires_text),
        reply_markup=device_card_keyboard(device.id, metadata.get("protocol", device.protocol)),
    )


async def _show_public_slot_card(callback: CallbackQuery, slot_index: int) -> None:
    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is not None and getattr(user, "is_blocked", False):
        await callback.message.answer(blocked_user_action_text(), parse_mode=ParseMode.HTML, reply_markup=blocked_home_keyboard)
        await callback.answer()
        return
    if user is None:
        await callback.message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
        return

    account_devices = await get_account_devices_for_user(int(user.id))
    device = next(
        (
            item
            for item in account_devices
            if str(item.get("kind") or "").strip().lower() == "public_slot"
            and int(item.get("id") or 0) == int(slot_index)
        ),
        None,
    )
    if device is None:
        await callback.message.answer(delete_device_not_found_text(), parse_mode=ParseMode.HTML)
        return

    access_expires_at = await get_access_expires_at(int(user.id))
    expires_text = access_expires_at.strftime("%Y-%m-%d %H:%M:%S") if access_expires_at else "—"
    await _edit_or_send(
        callback.message,
        _public_slot_card_text(device, expires_text),
        reply_markup=public_device_card_keyboard(int(slot_index)),
    )


@router.message(F.text == "📱 Устройства")
@router.message(F.text == "Устройства")
async def devices_handler(message: Message):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
        return

    await _show_devices_list(message, user)


@router.callback_query(F.data == "device:add")
async def add_device_callback(callback: CallbackQuery, state: FSMContext):
    user = await get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    if not has_active_access_from_user(user):
        await _edit_or_send(
            callback.message,
            access_required_text(),
            reply_markup=tariffs_keyboard(),
        )
        await callback.answer()
        return

    devices_count = await count_user_account_devices(user.id)
    limit_state = await _device_limit_state(user, devices_count)
    device_limit = limit_state["device_limit"]
    if devices_count >= device_limit:
        await _edit_or_send(
            callback.message,
            device_limit_reached_text(
                devices_count=devices_count,
                device_limit=device_limit,
                max_limit=MAX_DEVICE_LIMIT,
                can_buy_more=limit_state["can_buy_more"],
                price_rub=device_slot_unit_price_rub(),
                expires_at=limit_state["expires_text"],
                is_over_limit=limit_state["is_over_limit"],
            ),
            reply_markup=device_limit_reached_keyboard(can_buy_more=limit_state["can_buy_more"]),
        )
        await callback.answer()
        return

    await state.clear()
    await safe_emit_analytics_event(
        event_name=EVENT_CONNECTION_STARTED,
        user_id=int(user.id),
        telegram_id=int(callback.from_user.id),
        dedupe_key=f"connection-started:{int(user.id)}",
        payload={"entrypoint": "device_add"},
    )
    await state.set_state(DeviceStates.waiting_name)
    screen_message = await _edit_or_send(callback.message, ask_device_name_text())
    await state.update_data(
        create_flow=True,
        screen_chat_id=screen_message.chat.id,
        screen_message_id=screen_message.message_id,
    )
    await callback.answer()


@router.message(DeviceStates.waiting_name)
async def device_name_input(message: Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("✏ Отправь текстовое название устройства, например: <code>Телефон</code>.", parse_mode=ParseMode.HTML)
        return

    device_name = message.text.strip()[:64]
    await state.update_data(device_name=device_name)
    await _edit_message_by_state(
        message,
        state,
        ask_device_os_text(device_name),
        reply_markup=device_os_keyboard("device:os"),
    )


@router.callback_query(F.data.startswith("device:os:"))
async def device_os_callback(callback: CallbackQuery, state: FSMContext):
    os_type = callback.data.split(":")[2]
    data = await state.get_data()
    if not data.get("device_name"):
        await callback.message.answer("Сначала укажи название устройства.")
        await callback.answer()
        return

    await state.update_data(device_type=os_type)
    await _edit_or_send(
        callback.message,
        ask_device_country_text(data["device_name"], os_type),
        reply_markup=device_country_keyboard("device:createcountry", telegram_id=callback.from_user.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("device:mode:"))
@router.callback_query(F.data.startswith("device:protocol:"))
async def device_protocol_callback(callback: CallbackQuery, state: FSMContext):
    selection = callback.data.split(":")[2]
    data = await state.get_data()
    if not data.get("device_name") or not data.get("device_type"):
        await callback.message.answer("Начни создание устройства заново.")
        await callback.answer()
        return

    mode = normalize_mode(selection, default="") if is_mode_key(selection) else infer_mode_from_protocol(selection)
    await state.update_data(mode=mode)

    if data.get("country_code"):
        handled = await _create_device_from_selection(
            callback,
            state,
            country_code=normalize_country_code(data["country_code"]),
            mode=mode,
        )
        if not handled:
            await callback.answer()
        return
    else:
        await _edit_or_send(
            callback.message,
            ask_device_country_text(data["device_name"], data["device_type"]),
            reply_markup=device_country_keyboard("device:createcountry", telegram_id=callback.from_user.id, mode=mode),
        )
    await callback.answer()


async def _create_device_from_selection(callback: CallbackQuery, state: FSMContext, *, country_code: str, mode: str) -> bool:
    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
        return False
    provision_request_id = current_or_new_trace_id(prefix="dev")

    data = await state.get_data()
    device_name = data.get("device_name")
    device_type = data.get("device_type")
    if not device_name or not device_type:
        await callback.message.answer("Начни создание устройства заново.")
        return False

    selected_mode = normalize_mode(mode, default=get_auto_mode())
    resolved_mode = resolve_effective_mode(selected_mode, country_code)

    if not mode_available_for_user(selected_mode, telegram_id=callback.from_user.id):
        await callback.answer(
            "Мобильный режим пока ещё не открыт для всех пользователей.",
            show_alert=True,
        )
        await _edit_or_send(
            callback.message,
            mobile_mode_placeholder_text(country_code),
            reply_markup=device_protocol_keyboard(telegram_id=callback.from_user.id, country_code=country_code),
        )
        return True

    access_expires_at = await get_access_expires_at(user.id)
    if access_expires_at is None:
        await callback.message.answer(access_required_text(), parse_mode=ParseMode.HTML)
        return False

    capacity_error = await _region_capacity_error(country_code)
    if capacity_error:
        await callback.answer(capacity_error, show_alert=True)
        return True

    if not mode_supported_in_region(selected_mode, country_code, telegram_id=callback.from_user.id):
        await callback.answer("Этот регион пока не поддерживает выбранный режим.", show_alert=True)
        return True

    country_name = get_country_name(country_code)
    protocol = get_mode_protocol(selected_mode, country_code)
    await safe_emit_analytics_event(
        event_name=EVENT_CONNECTION_READY,
        user_id=int(user.id),
        telegram_id=int(callback.from_user.id),
        dedupe_key=f"connection-ready:{int(user.id)}",
        country_code=country_code,
        payload={
            "device_name": device_name,
            "device_type": device_type,
            "mode": selected_mode,
            "protocol": protocol,
            "country_code": country_code,
            "country_name": country_name,
        },
    )
    await safe_emit_analytics_event(
        event_name=EVENT_CONFIG_REQUESTED,
        user_id=int(user.id),
        telegram_id=int(callback.from_user.id),
        country_code=country_code,
        payload={
            "device_name": device_name,
            "device_type": device_type,
            "mode": selected_mode,
            "protocol": protocol,
            "country_code": country_code,
            "country_name": country_name,
        },
    )
    device = None
    metadata: dict | None = None
    created_device_id: int | None = None
    created_client_uuid: str | None = None
    created_email: str | None = None
    created_xui_client_id: str | None = None
    expires_text = access_expires_at.strftime("%Y-%m-%d %H:%M:%S")

    try:
        if protocol == "trojan":
            xui_client = XUIClient(country_code=country_code)
            try:
                success = await xui_client.login()
                if not success:
                    await callback.message.answer(PANEL_CONNECTION_ERROR_TEXT, parse_mode=ParseMode.HTML)
                    return False
                inbound = await xui_client.find_inbound("trojan", 8443)
                if inbound is None:
                    await callback.message.answer("Не удалось подготовить подключение. Попробуй ещё раз позже.")
                    return False
                email = f"trojan_{user.id}_{int(time.time())}"
                result = await xui_client.provision_trojan_client(
                    user_id=user.id,
                    email=email,
                    access_expires_at=access_expires_at,
                    save_callback=create_vpn_client,
                )
            finally:
                await xui_client.close()
            created_device_id = int(result["vpn_client_id"])
            created_client_uuid = str(result["client_uuid"])
            created_email = str(result["email"])
            created_xui_client_id = str(result["client_uuid"])
            connection_name = build_connection_name(country_code=country_code, country_name=country_name, email=result["email"])
            trojan_link = build_trojan_link(
                inbound=inbound,
                password=result["client_uuid"],
                email=result["email"],
                connection_name=connection_name,
                country_code=country_code,
            )
            metadata = {
                "device_name": device_name,
                "device_type": device_type,
                "mode": selected_mode,
                "resolved_mode": resolved_mode,
                "connection_profile": get_mode_connection_profile(selected_mode, country_code),
                "protocol": protocol,
                "inbound_id": result["inbound_id"],
                "trojan_link": trojan_link,
                "delivery_mode": _device_delivery_mode(protocol, device_type),
                "happ_confirmed": False,
                **build_region_snapshot(country_code),
            }
            await update_vpn_client_metadata(result["vpn_client_id"], metadata)
            device = await get_vpn_client_by_id(result["vpn_client_id"])
        else:
            email = f"device_{user.id}_{int(time.time())}"
            provisioner = get_vless_provisioner(country_code, build_region_snapshot(country_code).get("provider_type"))
            try:
                result = await provisioner.provision_vless_client(
                    user_id=user.id,
                    email=email,
                    access_expires_at=access_expires_at,
                    save_callback=create_vpn_client,
                    country_code=country_code,
                )
            finally:
                await provisioner.close()
            created_device_id = int(result.vpn_client_id)
            created_client_uuid = str(result.client_uuid)
            created_email = str(result.email)
            created_xui_client_id = None
            metadata = {
                "device_name": device_name,
                "device_type": device_type,
                "mode": selected_mode,
                "resolved_mode": resolved_mode,
                "connection_profile": get_mode_connection_profile(selected_mode, country_code),
                "protocol": protocol,
                "delivery_mode": _device_delivery_mode(protocol, device_type),
                "happ_confirmed": False,
                **build_region_snapshot(country_code),
                **result.metadata,
            }
            await update_vpn_client_metadata(result.vpn_client_id, metadata)
            device = await get_vpn_client_by_id(result.vpn_client_id)
    except Exception:
        logger.exception("Failed to create device for user_id=%s", user.id)
        if (
            created_device_id is not None
            and created_client_uuid is not None
            and created_email is not None
            and metadata is not None
        ):
            cleaned = await _cleanup_provisioned_device_after_failure(
                device_id=created_device_id,
                protocol=protocol,
                client_uuid=created_client_uuid,
                email=created_email,
                xui_client_id=created_xui_client_id,
                metadata=metadata,
            )
            if not cleaned:
                await enqueue_finalize_created_device_job(
                    device_id=created_device_id,
                    user_id=int(user.id),
                    protocol=protocol,
                    client_uuid=created_client_uuid,
                    email=created_email,
                    xui_client_id=created_xui_client_id,
                    metadata=metadata,
                    access_expires_at=access_expires_at,
                    request_id=provision_request_id,
                )
                logger.warning(
                    "Provisioning failure left finalize pending device_id=%s user_id=%s protocol=%s request_id=%s",
                    created_device_id,
                    user.id,
                    protocol,
                    provision_request_id,
                )
        await _emit_provisioning_failure_event(
            user.id,
            protocol,
            country_code,
            "provisioning failed",
            request_id=provision_request_id,
        )
        await callback.message.answer(PANEL_OPERATION_ERROR_TEXT, parse_mode=ParseMode.HTML)
        return False

    if device is None or metadata is None:
        logger.error(
            "Device provisioning completed but device fetch failed for user_id=%s protocol=%s country_code=%s",
            user.id,
            protocol,
            country_code,
        )
        cleaned = False
        if (
            created_device_id is not None
            and created_client_uuid is not None
            and created_email is not None
            and metadata is not None
        ):
            cleaned = await _cleanup_provisioned_device_after_failure(
                device_id=created_device_id,
                protocol=protocol,
                client_uuid=created_client_uuid,
                email=created_email,
                xui_client_id=created_xui_client_id,
                metadata=metadata,
            )
            if not cleaned:
                await enqueue_finalize_created_device_job(
                    device_id=created_device_id,
                    user_id=int(user.id),
                    protocol=protocol,
                    client_uuid=created_client_uuid,
                    email=created_email,
                    xui_client_id=created_xui_client_id,
                    metadata=metadata,
                    access_expires_at=access_expires_at,
                    request_id=provision_request_id,
                )
                logger.warning(
                    "Device fetch failure left finalize pending device_id=%s user_id=%s protocol=%s request_id=%s",
                    created_device_id,
                    user.id,
                    protocol,
                    provision_request_id,
                )
        await callback.message.answer(
            PANEL_OPERATION_ERROR_TEXT if cleaned else device_delivery_retry_text(device_name),
            parse_mode=ParseMode.HTML,
        )
        await state.clear()
        return False

    try:
        delivery_mode = metadata.get("delivery_mode")
        if delivery_mode == "mobile_happ":
            await _edit_or_send(
                callback.message,
                vless_happ_question_text(
                    device_name,
                    device_type,
                    country_name,
                    protocol_name=format_mode(selected_mode),
                ),
                reply_markup=device_happ_question_keyboard(device.id),
            )
            await _mark_trial_technical_engagement_safe(user.id)
        elif protocol == "trojan":
            await _edit_or_send(
                callback.message,
                trojan_delivery_text(device_name, device_type, country_name),
                reply_markup=device_instruction_keyboard(device.id, metadata.get("protocol", device.protocol)),
            )
            await _send_trojan_config(callback.message, device, metadata, expires_text)
            await _emit_credential_delivery_event(device, metadata, reissued=False)
        else:
            await _edit_or_send(
                callback.message,
                vless_delivery_text(
                    device_name,
                    device_type,
                    country_name,
                    mobile_happ=False,
                    protocol_name=format_mode(selected_mode),
                ),
                reply_markup=device_instruction_keyboard(device.id, metadata.get("protocol", device.protocol)),
            )
            await _send_vless_config(callback.message, device, metadata, expires_text)
            await _emit_credential_delivery_event(device, metadata, reissued=False)
    except Exception:
        logger.exception("Device created but delivery failed for device_id=%s", device.id)
        await _emit_delivery_failure_event(
            user.id,
            device.id,
            protocol,
            country_code,
            "delivery failed after provisioning",
            request_id=provision_request_id,
        )
        await callback.message.answer(device_delivery_retry_text(device_name), parse_mode=ParseMode.HTML)

    await state.clear()
    return False


@router.callback_query(F.data.startswith("device:createcountry:"))
async def device_create_country_callback(callback: CallbackQuery, state: FSMContext):
    country_code = callback.data.split(":")[2]

    data = await state.get_data()
    device_name = data.get("device_name")
    device_type = data.get("device_type")

    if not device_name or not device_type:
        await callback.message.answer("Начни создание устройства заново.")
        await callback.answer()
        return

    mode = normalize_mode(data.get("mode"), default="") if data.get("mode") else ""
    normalized_country = normalize_country_code(country_code)

    if mode:
        handled = await _create_device_from_selection(callback, state, country_code=normalized_country, mode=mode)
        if not handled:
            await callback.answer()
    else:
        await state.update_data(country_code=normalized_country)
        await _edit_or_send(
            callback.message,
            ask_device_protocol_text(device_name, device_type, normalized_country, telegram_id=callback.from_user.id),
            reply_markup=device_protocol_keyboard(telegram_id=callback.from_user.id, country_code=normalized_country),
        )
        await callback.answer()


@router.callback_query(F.data.startswith("device:happ:prompt:"))
async def device_happ_prompt_callback(callback: CallbackQuery):
    device_id = int(callback.data.split(":")[3])
    user, device = await _get_owned_device_for_telegram(callback.from_user.id, device_id)
    if user is None:
        await callback.message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return
    if device is None:
        await callback.message.answer(delete_device_not_found_text(), parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    metadata = _device_metadata(device)
    protocol_name = _protocol_delivery_name(metadata.get("protocol", device.protocol), metadata)
    await _edit_or_send(
        callback.message,
        vless_happ_question_text(
            metadata.get("device_name", device.email),
            metadata.get("device_type", "android"),
            metadata.get("country_name", "Германия"),
            protocol_name=protocol_name,
        ),
        reply_markup=device_happ_question_keyboard(device.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("device:happ:installed:"))
async def device_happ_installed_callback(callback: CallbackQuery):
    device_id = int(callback.data.split(":")[3])
    user, device = await _get_owned_device_for_telegram(callback.from_user.id, device_id)
    if user is None:
        await callback.message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return
    if device is None:
        await callback.message.answer(delete_device_not_found_text(), parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    metadata = _device_metadata(device)
    metadata["happ_confirmed"] = True
    await update_vpn_client_metadata(device.id, metadata)
    access_expires_at = await get_access_expires_at(device.user_id)
    expires_text = access_expires_at.strftime("%Y-%m-%d %H:%M:%S") if access_expires_at else "—"
    protocol_name = _protocol_delivery_name(metadata.get("protocol", device.protocol), metadata)

    await _edit_or_send(
        callback.message,
        vless_delivery_text(
            metadata.get("device_name", device.email),
            metadata.get("device_type", "android"),
            metadata.get("country_name", "Германия"),
            mobile_happ=True,
            protocol_name=protocol_name,
        ),
        reply_markup=device_instruction_keyboard(device.id, metadata.get("protocol", device.protocol)),
    )
    await _send_device_config(callback.message, device, metadata, expires_text)
    await _emit_credential_delivery_event(device, metadata, reissued=False)
    await callback.answer()


@router.callback_query(F.data.startswith("device:happ:notinstalled:"))
async def device_happ_not_installed_callback(callback: CallbackQuery):
    device_id = int(callback.data.split(":")[3])
    user, device = await _get_owned_device_for_telegram(callback.from_user.id, device_id)
    if user is None:
        await callback.message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return
    if device is None:
        await callback.message.answer(delete_device_not_found_text(), parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    metadata = _device_metadata(device)
    protocol_name = _protocol_delivery_name(metadata.get("protocol", device.protocol), metadata)
    await _edit_or_send(
        callback.message,
        vless_happ_download_text(
            metadata.get("device_name", device.email),
            metadata.get("device_type", "android"),
            metadata.get("country_name", "Германия"),
            protocol_name=protocol_name,
        ),
        reply_markup=device_happ_install_keyboard(device.id, metadata.get("device_type", "android")),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("device:happ:ready:"))
async def device_happ_ready_callback(callback: CallbackQuery):
    device_id = int(callback.data.split(":")[3])
    user, device = await _get_owned_device_for_telegram(callback.from_user.id, device_id)
    if user is None:
        await callback.message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return
    if device is None:
        await callback.message.answer(delete_device_not_found_text(), parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    metadata = _device_metadata(device)
    metadata["happ_confirmed"] = True
    await update_vpn_client_metadata(device.id, metadata)
    access_expires_at = await get_access_expires_at(device.user_id)
    expires_text = access_expires_at.strftime("%Y-%m-%d %H:%M:%S") if access_expires_at else "—"
    protocol_name = _protocol_delivery_name(metadata.get("protocol", device.protocol), metadata)

    await _edit_or_send(
        callback.message,
        vless_delivery_text(
            metadata.get("device_name", device.email),
            metadata.get("device_type", "android"),
            metadata.get("country_name", "Германия"),
            mobile_happ=True,
            protocol_name=protocol_name,
        ),
        reply_markup=device_instruction_keyboard(device.id, metadata.get("protocol", device.protocol)),
    )
    await _send_device_config(callback.message, device, metadata, expires_text)
    await _emit_credential_delivery_event(device, metadata, reissued=False)
    await callback.answer("Ссылка уже готова")


@router.callback_query(F.data.startswith("device:guide:"))
async def device_guide_callback(callback: CallbackQuery):
    device_id = int(callback.data.split(":")[2])
    user, device = await _get_owned_device_for_telegram(callback.from_user.id, device_id)
    if user is None:
        await callback.message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return
    if device is None:
        await callback.message.answer(delete_device_not_found_text(), parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    metadata = _device_metadata(device)
    if metadata.get("delivery_mode") == "mobile_happ" and not metadata.get("happ_confirmed"):
        keyboard = device_happ_install_keyboard(device.id, metadata.get("device_type", "android"))
    else:
        keyboard = device_instruction_keyboard(device.id, metadata.get("protocol", device.protocol))
    await _edit_or_send(
        callback.message,
        device_guide_text(
            metadata.get("protocol", device.protocol),
            metadata.get("device_type", "other"),
            metadata.get("device_name", device.email),
            metadata.get("country_name", "Германия"),
        ),
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("device:view:"))
async def device_view_callback(callback: CallbackQuery):
    parsed = _parse_device_target_callback(callback.data, action="view")
    if parsed is None:
        await callback.answer(delete_device_not_found_text(), show_alert=True)
        return

    device_kind, device_id = parsed
    if device_kind == "public_slot":
        await _show_public_slot_card(callback, device_id)
    else:
        await _show_device_card(callback, device_id)
    await callback.answer()


@router.callback_query(F.data.startswith("device:public:view:"))
async def device_public_view_callback(callback: CallbackQuery):
    slot_index = int(callback.data.split(":")[3])
    await _show_public_slot_card(callback, slot_index)
    await callback.answer()


@router.callback_query(F.data == "device:back")
async def device_back_callback(callback: CallbackQuery):
    await _show_user_home_from_callback(callback)


@router.callback_query(F.data.startswith("device:settings:close:"))
async def device_settings_close_callback(callback: CallbackQuery):
    device_id = int(callback.data.split(":")[3])
    await _show_device_card(callback, device_id)
    await callback.answer()


@router.callback_query(F.data.startswith("device:settings:"))
async def device_settings_callback(callback: CallbackQuery):
    device_id = int(callback.data.split(":")[2])
    user, device = await _get_owned_device_for_telegram(callback.from_user.id, device_id)
    if user is None:
        await callback.message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return
    if device is None:
        await callback.message.answer(delete_device_not_found_text(), parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    metadata = _device_metadata(device)
    access_expires_at = await get_access_expires_at(device.user_id)
    expires_text = access_expires_at.strftime("%Y-%m-%d %H:%M:%S") if access_expires_at else "—"
    await _edit_or_send(
        callback.message,
        device_settings_text(metadata, expires_text),
        reply_markup=device_settings_keyboard(device_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("device:rename:"))
async def device_rename_start_callback(callback: CallbackQuery, state: FSMContext):
    device_id = int(callback.data.split(":")[2])
    user, device = await _get_owned_device_for_telegram(callback.from_user.id, device_id)
    if user is None:
        await callback.message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return
    if device is None:
        await callback.message.answer(delete_device_not_found_text(), parse_mode=ParseMode.HTML)
        await callback.answer()
        return
    await state.set_state(DeviceStates.waiting_rename)
    screen_message = await _edit_or_send(callback.message, "✏ <b>Введи новое название устройства.</b>")
    await state.update_data(
        rename_device_id=device_id,
        screen_chat_id=screen_message.chat.id,
        screen_message_id=screen_message.message_id,
    )
    await callback.answer()


@router.message(DeviceStates.waiting_rename)
async def device_rename_input(message: Message, state: FSMContext):
    data = await state.get_data()
    device_id = data.get("rename_device_id")
    if device_id is None:
        await state.clear()
        return

    user, device = await _get_owned_device_for_telegram(message.from_user.id, device_id)
    if user is None:
        await message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
        await state.clear()
        return
    if device is None:
        await message.answer(delete_device_not_found_text(), parse_mode=ParseMode.HTML)
        await state.clear()
        return

    if not message.text or not message.text.strip():
        await message.answer("✏ Отправь новое текстовое название устройства.", parse_mode=ParseMode.HTML)
        return

    metadata = _device_metadata(device)
    metadata["device_name"] = message.text.strip()[:64]
    await update_vpn_client_metadata(device_id, metadata)
    access_expires_at = await get_access_expires_at(device.user_id)
    expires_text = access_expires_at.strftime("%Y-%m-%d %H:%M:%S") if access_expires_at else "—"
    await _edit_message_by_state(
        message,
        state,
        device_settings_text(metadata, expires_text),
        reply_markup=device_settings_keyboard(device_id),
    )
    await state.clear()


@router.callback_query(F.data.startswith("device:oschange:"))
async def device_os_change_callback(callback: CallbackQuery):
    device_id = int(callback.data.split(":")[2])
    user, device = await _get_owned_device_for_telegram(callback.from_user.id, device_id)
    if user is None:
        await callback.message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return
    if device is None:
        await callback.message.answer(delete_device_not_found_text(), parse_mode=ParseMode.HTML)
        await callback.answer()
        return
    await _edit_or_send(
        callback.message,
        "🖥 Выбери новую ОС устройства.",
        reply_markup=device_os_keyboard(f"device:updateos:{device_id}"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("device:updateos:"))
async def device_update_os_callback(callback: CallbackQuery):
    _, _, device_id_str, os_type = callback.data.split(":")
    device_id = int(device_id_str)
    user, device = await _get_owned_device_for_telegram(callback.from_user.id, device_id)
    if user is None:
        await callback.message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return
    if device is None:
        await callback.message.answer(delete_device_not_found_text(), parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    metadata = _device_metadata(device)
    metadata["device_type"] = os_type
    await update_vpn_client_metadata(device_id, metadata)
    access_expires_at = await get_access_expires_at(device.user_id)
    expires_text = access_expires_at.strftime("%Y-%m-%d %H:%M:%S") if access_expires_at else "—"
    await _edit_or_send(
        callback.message,
        device_settings_text(metadata, expires_text),
        reply_markup=device_settings_keyboard(device_id),
    )
    await callback.answer("ОС устройства обновлена", show_alert=False)


async def _apply_existing_device_selection(callback: CallbackQuery, device, metadata: dict, *, target_country_code: str, selected_mode: str) -> None:
    current_country_code = normalize_country_code(metadata.get("country_code"))

    if not mode_available_for_user(selected_mode, telegram_id=callback.from_user.id):
        await callback.answer(
            "Мобильный режим пока ещё не открыт для всех пользователей.",
            show_alert=True,
        )
        await _edit_or_send(
            callback.message,
            mobile_mode_placeholder_text(target_country_code),
            reply_markup=device_protocol_keyboard_for_existing(
                device.id,
                target_country_code,
                telegram_id=callback.from_user.id,
            ),
        )
        return

    if is_cross_region_change(current_country_code, target_country_code):
        await callback.answer(
            "Для смены страны пересоздай устройство.",
            show_alert=True,
        )
        await _edit_or_send(
            callback.message,
            device_region_recreate_required_text(current_country_code, target_country_code),
            reply_markup=device_card_keyboard(device.id, metadata.get("protocol", device.protocol)),
        )
        return

    current_effective_mode = resolve_effective_mode(metadata.get("mode"), current_country_code, protocol=device.protocol, metadata=metadata)
    requested_effective_mode = resolve_effective_mode(selected_mode, target_country_code, protocol=device.protocol, metadata=metadata)
    if requested_effective_mode != current_effective_mode:
        await callback.answer(
            "Для готового устройства смена режима пока недоступна. Проще пересоздать устройство с новым режимом.",
            show_alert=True,
        )
        return

    metadata["mode"] = selected_mode
    metadata["resolved_mode"] = requested_effective_mode
    metadata["connection_profile"] = get_mode_connection_profile(selected_mode, target_country_code)
    metadata["protocol"] = get_mode_protocol(selected_mode, target_country_code)
    metadata.update(build_region_snapshot(target_country_code))
    await update_vpn_client_metadata(device.id, metadata)
    access_expires_at = await get_access_expires_at(device.user_id)
    expires_text = access_expires_at.strftime("%Y-%m-%d %H:%M:%S") if access_expires_at else "—"
    await _edit_or_send(
        callback.message,
        device_card_text(metadata, expires_text),
        reply_markup=device_card_keyboard(device.id, metadata.get("protocol", device.protocol)),
    )
    await _emit_device_country_changed_event(device, current_country_code, target_country_code)
    await callback.answer("Параметры подключения обновлены", show_alert=False)


@router.callback_query(F.data.startswith("device:country:"))
async def device_country_change_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) == 4:
        _, _, device_id_str, country_code = parts
        selection = None
    else:
        _, _, device_id_str, selection, country_code = parts
    device_id = int(device_id_str)
    user, device = await _get_owned_device_for_telegram(callback.from_user.id, device_id)
    if user is None:
        await callback.message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return
    if device is None:
        await callback.message.answer(delete_device_not_found_text(), parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    capacity_error = await _region_capacity_error(country_code)
    if capacity_error:
        await callback.answer(capacity_error, show_alert=True)
        return

    metadata = _device_metadata(device)
    target_country_code = normalize_country_code(country_code)

    if selection is None:
        current_country_code = normalize_country_code(metadata.get("country_code"))
        if is_cross_region_change(current_country_code, target_country_code):
            await callback.answer(
                "Для смены страны пересоздай устройство.",
                show_alert=True,
            )
            await _edit_or_send(
                callback.message,
                device_region_recreate_required_text(current_country_code, target_country_code),
                reply_markup=device_card_keyboard(device_id, metadata.get("protocol", device.protocol)),
            )
            return
        await _edit_or_send(
            callback.message,
            ask_existing_device_protocol_text(
                metadata.get("device_name", device.email),
                get_country_name(target_country_code),
            ),
            reply_markup=device_protocol_keyboard_for_existing(device_id, target_country_code),
        )
        await callback.answer()
        return

    selected_mode = normalize_mode(selection, default="") if is_mode_key(selection) else infer_mode_from_protocol(selection, metadata)
    await _apply_existing_device_selection(
        callback,
        device,
        metadata,
        target_country_code=target_country_code,
        selected_mode=selected_mode,
    )


@router.callback_query(F.data.startswith("device:location:"))
async def device_location_callback(callback: CallbackQuery):
    device_id = int(callback.data.split(":")[2])
    user, device = await _get_owned_device_for_telegram(callback.from_user.id, device_id)
    if user is None:
        await callback.message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return
    if device is None:
        await callback.message.answer(delete_device_not_found_text(), parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    metadata = _device_metadata(device)
    current_country_code = normalize_country_code(metadata.get("country_code"))
    await _edit_or_send(
        callback.message,
        ask_existing_device_protocol_text(
            metadata.get("device_name", device.email),
            metadata.get("country_name"),
            telegram_id=callback.from_user.id,
            country_code=current_country_code,
        ),
        reply_markup=device_protocol_keyboard_for_existing(
            device_id,
            current_country_code,
            telegram_id=callback.from_user.id,
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("device:remode:"))
@router.callback_query(F.data.startswith("device:reprotocol:"))
async def device_reprotocol_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) == 4:
        _, _, device_id_str, selection = parts
        country_code = None
    else:
        _, _, device_id_str, country_code, selection = parts
    device_id = int(device_id_str)
    user, device = await _get_owned_device_for_telegram(callback.from_user.id, device_id)
    if user is None:
        await callback.message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return
    if device is None:
        await callback.message.answer(delete_device_not_found_text(), parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    metadata = _device_metadata(device)
    requested_mode = normalize_mode(selection, default="") if is_mode_key(selection) else infer_mode_from_protocol(selection, metadata)

    if country_code is None:
        await _edit_or_send(
            callback.message,
            ask_existing_device_protocol_text(
                metadata.get("device_name", device.email),
                metadata.get("country_name"),
                telegram_id=callback.from_user.id,
                country_code=normalize_country_code(metadata.get("country_code")),
            ),
            reply_markup=device_protocol_keyboard_for_existing(
                device_id,
                normalize_country_code(metadata.get("country_code")),
                telegram_id=callback.from_user.id,
            ),
        )
        await callback.answer()
        return

    await _apply_existing_device_selection(
        callback,
        device,
        metadata,
        target_country_code=normalize_country_code(country_code),
        selected_mode=requested_mode,
    )


@router.callback_query(F.data.startswith("device:config:"))
async def device_config_callback(callback: CallbackQuery):
    device_id = int(callback.data.split(":")[2])
    user, device = await _get_owned_device_for_telegram(callback.from_user.id, device_id)
    if user is None:
        await callback.message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return
    if device is None:
        await callback.message.answer(delete_device_not_found_text(), parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    metadata = _device_metadata(device)
    access_expires_at = await get_access_expires_at(device.user_id)
    expires_text = access_expires_at.strftime("%Y-%m-%d %H:%M:%S") if access_expires_at else "—"

    if device.protocol in {"vless", "trojan"} and metadata.get("delivery_mode") == "mobile_happ" and not metadata.get("happ_confirmed"):
        protocol_name = _protocol_delivery_name(device.protocol, metadata)
        await _edit_or_send(
            callback.message,
            vless_happ_download_text(
                metadata.get("device_name", device.email),
                metadata.get("device_type", "android"),
                metadata.get("country_name", "Германия"),
                protocol_name=protocol_name,
            ),
            reply_markup=device_happ_install_keyboard(device.id, metadata.get("device_type", "android")),
        )
        await callback.answer("Сначала установи Happ", show_alert=True)
        return

    await _enforce_device_key_limit(device, metadata, access_expires_at)
    await _send_device_config(callback.message, device, metadata, expires_text)
    await _emit_credential_delivery_event(device, metadata, reissued=True)
    await callback.answer()


@router.callback_query(F.data.startswith("device:routing:"))
async def device_routing_callback(callback: CallbackQuery):
    device_id = int(callback.data.split(":")[2])
    user, device = await _get_owned_device_for_telegram(callback.from_user.id, device_id)
    if user is None:
        await callback.message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return
    if device is None:
        await callback.message.answer(delete_device_not_found_text(), parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    metadata = _device_metadata(device)
    spec, payload = build_split_routing_pack_for_device(metadata.get("device_type", "other"))
    pack_file = BufferedInputFile(
        dumps_pack(payload),
        filename=spec.filename,
    )
    await callback.message.answer_document(
        document=pack_file,
        caption=split_routing_pack_text(metadata.get("device_name", device.email), spec.target_client),
        parse_mode=ParseMode.HTML,
    )
    await _mark_trial_technical_engagement_safe(device.user_id)
    await callback.answer("Пакет маршрутизации готов")


@router.callback_query(F.data.startswith("device:qr:"))
async def device_qr_callback(callback: CallbackQuery):
    device_id = int(callback.data.split(":")[2])
    user, device = await _get_owned_device_for_telegram(callback.from_user.id, device_id)
    if user is None:
        await callback.message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return
    if device is None:
        await callback.message.answer(delete_device_not_found_text(), parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    metadata = _device_metadata(device)
    access_expires_at = await get_access_expires_at(device.user_id)
    if device.protocol in {"vless", "trojan"} and metadata.get("delivery_mode") == "mobile_happ" and not metadata.get("happ_confirmed"):
        protocol_name = _protocol_delivery_name(device.protocol, metadata)
        await _edit_or_send(
            callback.message,
            vless_happ_download_text(
                metadata.get("device_name", device.email),
                metadata.get("device_type", "android"),
                metadata.get("country_name", "Германия"),
                protocol_name=protocol_name,
            ),
            reply_markup=device_happ_install_keyboard(device.id, metadata.get("device_type", "android")),
        )
        await callback.answer("Сначала установи Happ", show_alert=True)
        return

    await _enforce_device_key_limit(device, metadata, access_expires_at)
    payload = _resolve_connection_uri(device, metadata)

    if not payload:
        await callback.message.answer(PANEL_OPERATION_ERROR_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    qr_buffer = generate_qr_image(payload)
    qr_file = BufferedInputFile(qr_buffer.getvalue(), filename="amonora_qr.png")
    await callback.message.answer_photo(photo=qr_file)
    await _mark_trial_technical_engagement_safe(device.user_id)
    await callback.answer()


@router.callback_query(F.data.startswith("device:delete:"))
async def delete_device_callback(callback: CallbackQuery):
    parsed = _parse_device_target_callback(callback.data, action="delete")
    if parsed is None:
        await callback.message.answer(delete_device_not_found_text(), parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    device_kind, device_id = parsed
    if device_kind == "public_slot":
        user = await get_user_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
            await callback.answer()
            return

        cleared = await clear_public_subscription_device_slot_binding(
            int(user.id),
            slot_index=device_id,
            binding_keys=PUBLIC_SUBSCRIPTION_BINDING_METADATA_KEYS,
        )
        if not cleared:
            await callback.message.answer(delete_device_not_found_text(), parse_mode=ParseMode.HTML)
            await callback.answer()
            return

        await _show_devices_list(callback.message, user)
        await callback.answer()
        return

    user, vpn_client = await _get_owned_device_for_telegram(callback.from_user.id, device_id)
    if not user:
        await callback.message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    if vpn_client is None:
        await callback.message.answer(delete_device_not_found_text(), parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    client_data = json.loads(vpn_client.client_data) if vpn_client.client_data else {}
    country_code = client_data.get("country_code") or "de"
    try:
        inbound_id = client_data.get("inbound_id")

        if vpn_client.protocol == "vless":
            provisioner = get_vless_provisioner(country_code, client_data.get("provider_type"))
            result = await provisioner.delete_vless_client(
                client_uuid=vpn_client.xui_client_id or vpn_client.client_uuid,
                email=vpn_client.email,
                metadata=client_data,
            )
            await provisioner.close()
        elif vpn_client.protocol == "trojan":
            xui_client = XUIClient(country_code=country_code)
            try:
                success = await xui_client.login()
                if not success:
                    await callback.message.answer(PANEL_CONNECTION_ERROR_TEXT, parse_mode=ParseMode.HTML)
                    return
                result = await xui_client.delete_trojan_client(
                    inbound_id=inbound_id or 4,
                    client_uuid=vpn_client.xui_client_id or vpn_client.client_uuid,
                    email=vpn_client.email,
                )
            finally:
                await xui_client.close()
        else:
            await callback.message.answer(PANEL_OPERATION_ERROR_TEXT, parse_mode=ParseMode.HTML)
            return

        if not result.get("success"):
            await callback.message.answer(PANEL_OPERATION_ERROR_TEXT, parse_mode=ParseMode.HTML)
            return

        deleted = await delete_vpn_client_and_return(device_id)
        if deleted:
            await _show_devices_list(callback.message, user)
        else:
            await callback.message.answer(delete_device_not_found_text(), parse_mode=ParseMode.HTML)
    except Exception:
        logger.exception("Failed to delete VPN device id=%s", device_id)
        await callback.message.answer(PANEL_OPERATION_ERROR_TEXT, parse_mode=ParseMode.HTML)
    finally:
        await callback.answer()


@router.callback_query(F.data.startswith("device:public:delete:"))
async def delete_public_device_callback(callback: CallbackQuery):
    parsed = _parse_device_target_callback(callback.data, action="delete")
    slot_index = parsed[1] if parsed is not None else int(callback.data.split(":")[3])
    user = await get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.message.answer(USER_NOT_FOUND_TEXT, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    cleared = await clear_public_subscription_device_slot_binding(
        int(user.id),
        slot_index=slot_index,
        binding_keys=PUBLIC_SUBSCRIPTION_BINDING_METADATA_KEYS,
    )
    if not cleared:
        await callback.message.answer(delete_device_not_found_text(), parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    await _show_devices_list(callback.message, user)
    await callback.answer()
