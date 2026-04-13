from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy import delete, select

from backend.core.database import async_session
from backend.core.models import VpnClientActivation
from bot.db import activate_vpn_client_device, get_user_by_id, get_vpn_client_by_id
from bot.utils.access import has_active_access_from_user
from bot.utils.vless import build_trojan_link_from_metadata, build_vless_link_from_metadata
from dashboard.services import reissue_vpn_client_device
from test_bot.profiles import TestProfile, build_test_profile_link, get_test_profile


TEST_SWITCH_DEVICE_CHOICES: dict[str, dict[str, str]] = {
    "iphone": {
        "label": "iPhone",
        "platform": "ios",
        "app_version": "testbot-ios",
    },
    "windows": {
        "label": "Windows PC",
        "platform": "windows",
        "app_version": "testbot-windows",
    },
}


@dataclass(frozen=True)
class TestProfileRuntime:
    profile: TestProfile
    link: str
    active_device_label: str | None
    active_platform: str | None
    last_activated_at: object | None
    supports_transfer: bool


def _hash_test_fingerprint(profile_key: str, device_key: str) -> str:
    return hashlib.sha256(f"testbot:{profile_key}:{device_key}".encode("utf-8")).hexdigest()


async def _list_activations(vpn_client_id: int) -> list[VpnClientActivation]:
    async with async_session() as session:
        result = await session.execute(
            select(VpnClientActivation).where(VpnClientActivation.vpn_client_id == int(vpn_client_id))
        )
        return list(result.scalars().all())


async def _clear_activations(vpn_client_id: int) -> None:
    async with async_session() as session:
        await session.execute(delete(VpnClientActivation).where(VpnClientActivation.vpn_client_id == int(vpn_client_id)))
        await session.commit()


def _build_runtime_link(profile: TestProfile, vpn_client) -> str:
    metadata = json.loads(vpn_client.client_data) if vpn_client.client_data else {}
    if vpn_client.protocol == "trojan":
        return build_trojan_link_from_metadata(
            metadata,
            password=vpn_client.client_uuid,
            email=vpn_client.email,
            connection_name=profile.connection_name,
            country_code=profile.country_code,
        )
    return build_vless_link_from_metadata(
        metadata,
        client_uuid=vpn_client.client_uuid,
        email=vpn_client.email,
        connection_name=profile.connection_name,
        country_code=profile.country_code,
    )


def _latest_activation(activations: list[VpnClientActivation]) -> VpnClientActivation | None:
    if not activations:
        return None
    return max(
        activations,
        key=lambda row: row.last_activated_at or row.first_activated_at,
    )


async def get_test_profile_runtime(profile_key: str) -> TestProfileRuntime | None:
    profile = get_test_profile(profile_key)
    if profile is None:
        return None

    if not profile.vpn_client_id:
        return TestProfileRuntime(
            profile=profile,
            link=build_test_profile_link(profile),
            active_device_label=None,
            active_platform=None,
            last_activated_at=None,
            supports_transfer=False,
        )

    vpn_client = await get_vpn_client_by_id(profile.vpn_client_id)
    if vpn_client is None:
        return TestProfileRuntime(
            profile=profile,
            link=build_test_profile_link(profile),
            active_device_label="устройство не найдено",
            active_platform=None,
            last_activated_at=None,
            supports_transfer=True,
        )

    activations = await _list_activations(vpn_client.id)
    current = _latest_activation(activations)
    return TestProfileRuntime(
        profile=profile,
        link=_build_runtime_link(profile, vpn_client),
        active_device_label=current.device_label if current is not None else None,
        active_platform=current.platform if current is not None else None,
        last_activated_at=current.last_activated_at if current is not None else None,
        supports_transfer=True,
    )


async def activate_test_profile_device(profile_key: str, device_key: str, *, actor_telegram_id: int | None = None) -> dict:
    profile = get_test_profile(profile_key)
    if profile is None:
        raise ValueError("Профиль не найден")
    if not profile.vpn_client_id:
        raise ValueError("Для этого профиля переключение устройства не поддерживается")

    device_choice = TEST_SWITCH_DEVICE_CHOICES.get(device_key)
    if device_choice is None:
        raise ValueError("Неизвестное тестовое устройство")

    vpn_client = await get_vpn_client_by_id(profile.vpn_client_id)
    if vpn_client is None:
        raise ValueError("Устройство не найдено")

    user = await get_user_by_id(vpn_client.user_id)
    if user is None or not has_active_access_from_user(user):
        raise ValueError("У пользователя нет активного доступа")

    fingerprint_hash = _hash_test_fingerprint(profile.key, device_key)
    current_activations = await _list_activations(vpn_client.id)
    current = _latest_activation(current_activations)
    current_fingerprint = current.fingerprint_hash if current is not None else None
    previous_device_label = current.device_label if current is not None else None
    switched = bool(current is not None and current_fingerprint != fingerprint_hash)

    if switched:
        await reissue_vpn_client_device(vpn_client.id)
        await _clear_activations(vpn_client.id)
        vpn_client = await get_vpn_client_by_id(vpn_client.id)
        if vpn_client is None:
            raise ValueError("Устройство исчезло после перевыпуска")

    activation = await activate_vpn_client_device(
        vpn_client_id=vpn_client.id,
        user_id=vpn_client.user_id,
        country_code=profile.country_code,
        fingerprint_hash=fingerprint_hash,
        device_label=device_choice["label"],
        platform=device_choice["platform"],
        app_version=device_choice["app_version"],
        source_ip=(f"testbot:{actor_telegram_id}" if actor_telegram_id is not None else "testbot")[:64],
        user_agent="Amonora Test Bot",
        max_devices=1,
    )
    if activation["status"] != "ok":
        raise ValueError(f"Не удалось активировать ключ: {activation['status']}")

    runtime = await get_test_profile_runtime(profile_key)
    if runtime is None:
        raise ValueError("Не удалось обновить состояние профиля")

    return {
        "status": "transferred" if switched else "activated",
        "previous_device_label": previous_device_label,
        "runtime": runtime,
    }
