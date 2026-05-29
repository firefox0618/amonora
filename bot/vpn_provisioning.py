import asyncio
import json
import shlex
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from bot.config import config
from bot.utils.regions import (
    build_region_snapshot,
    get_country_provider_type,
)
from bot.utils.vless import (
    build_connection_name,
    build_vless_link,
    build_vless_link_from_metadata,
    extract_vless_transport_metadata,
)
from bot.vpn_api import XUIClient


@dataclass(frozen=True)
class VlessProvisionedClient:
    vpn_client_id: int
    client_uuid: str
    email: str
    metadata: dict[str, Any]


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_alpn(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = [value]
    return [str(item).strip() for item in raw_items if str(item).strip()]


def _normalize_xray_profile(
    profile: dict[str, Any],
    *,
    default_port: int,
) -> dict[str, Any]:
    normalized = {
        "port": _coerce_int(profile.get("port"), default_port),
        "reality_server_name": str(profile.get("reality_server_name") or ""),
        "reality_short_id": str(profile.get("reality_short_id") or ""),
        "reality_public_key": str(profile.get("reality_public_key") or profile.get("reality_password") or ""),
        "reality_password": str(profile.get("reality_password") or profile.get("reality_public_key") or ""),
        "xhttp_path": str(profile.get("xhttp_path") or ""),
        "stream_network": str(profile.get("stream_network") or "xhttp"),
        "transport_label": str(profile.get("transport_label") or "XHTTP"),
        "stream_path": str(profile.get("xhttp_path") or profile.get("stream_path") or ""),
        "stream_host": str(profile.get("stream_host") or ""),
        "stream_mode": str(profile.get("stream_mode") or "auto"),
        "mode_policy": str(profile.get("mode_policy") or profile.get("stream_mode") or "auto"),
        "fingerprint": str(profile.get("fingerprint") or "chrome"),
        "alpn": _normalize_alpn(profile.get("alpn")),
        "h3_preferred": _coerce_bool(profile.get("h3_preferred"), False),
        "h2_fallback": _coerce_bool(profile.get("h2_fallback"), False),
    }
    return normalized


def _normalize_xray_core_meta(meta: dict[str, Any]) -> dict[str, Any]:
    default_port = _coerce_int(meta.get("port"), 443)
    raw_profiles = meta.get("profiles") or {
        "primary": {
            "port": meta.get("port"),
            "reality_server_name": meta.get("reality_server_name"),
            "reality_short_id": meta.get("reality_short_id"),
            "reality_public_key": meta.get("reality_public_key"),
            "reality_password": meta.get("reality_password"),
            "xhttp_path": meta.get("xhttp_path"),
            "stream_network": meta.get("stream_network"),
            "transport_label": meta.get("transport_label"),
            "stream_path": meta.get("stream_path"),
            "stream_host": meta.get("stream_host"),
            "stream_mode": meta.get("stream_mode"),
            "mode_policy": meta.get("mode_policy"),
            "fingerprint": meta.get("fingerprint"),
            "alpn": meta.get("alpn"),
            "h3_preferred": meta.get("h3_preferred"),
            "h2_fallback": meta.get("h2_fallback"),
        }
    }
    profiles = {
        str(name): _normalize_xray_profile(dict(profile or {}), default_port=default_port)
        for name, profile in raw_profiles.items()
    }
    active_profile = str(meta.get("active_profile") or "primary")
    if active_profile not in profiles:
        active_profile = "primary" if "primary" in profiles else next(iter(profiles.keys()))

    return {
        "active_profile": active_profile,
        "profiles": profiles,
        "mtu_default": _coerce_int(meta.get("mtu_default"), 1400),
        "mtu_fallback": _coerce_int(meta.get("mtu_fallback"), 1420),
        "compatibility_fallback_region": str(meta.get("compatibility_fallback_region") or "de"),
        "dns_servers": [str(item).strip() for item in meta.get("dns_servers") or [] if str(item).strip()],
    }


def _resolve_xray_profile_name(normalized_meta: dict[str, Any], base_metadata: dict[str, Any] | None = None) -> str:
    payload = dict(base_metadata or {})
    requested_profile = str(payload.get("connection_profile") or "").strip()
    if requested_profile in normalized_meta["profiles"]:
        return requested_profile
    if str(payload.get("mode") or "").strip().lower() in {"mobile", "reserve", "white"} and "reserve" in normalized_meta["profiles"]:
        return "reserve"
    return normalized_meta["active_profile"]


class VPNProvisioner(ABC):
    provider_type: str

    @abstractmethod
    async def health_check(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def provision_vless_client(
        self,
        *,
        user_id: int,
        email: str,
        access_expires_at: datetime,
        save_callback,
        country_code: str,
    ) -> VlessProvisionedClient:
        raise NotImplementedError

    @abstractmethod
    async def sync_vless_client(
        self,
        *,
        client_uuid: str,
        email: str,
        metadata: dict[str, Any],
        access_expires_at: datetime | None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_vless_client(
        self,
        *,
        client_uuid: str,
        email: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def build_vless_metadata(
        self,
        *,
        client_uuid: str,
        email: str,
        country_code: str,
        base_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def close(self) -> None:
        return None


class XUIProvisioner(VPNProvisioner):
    provider_type = "xui"

    def __init__(self, country_code: str) -> None:
        self.country_code = country_code
        self.client = XUIClient(country_code=country_code)

    async def _ensure_logged_in(self) -> None:
        if not await self.client.login():
            raise ValueError(f"3x-ui login failed for country_code={self.country_code}")

    async def health_check(self) -> bool:
        return await self.client.login()

    async def provision_vless_client(
        self,
        *,
        user_id: int,
        email: str,
        access_expires_at: datetime,
        save_callback,
        country_code: str,
    ) -> VlessProvisionedClient:
        await self._ensure_logged_in()
        inbound = await self.client.find_inbound("vless", 443)
        if inbound is None:
            raise ValueError("VLESS inbound on port 443 not found")

        result = await self.client.provision_vless_client(
            user_id=user_id,
            email=email,
            access_expires_at=access_expires_at,
            save_callback=save_callback,
        )
        metadata = await self.build_vless_metadata(
            client_uuid=result["client_uuid"],
            email=result["email"],
            country_code=country_code,
            base_metadata={"inbound_id": result["inbound_id"]},
        )
        return VlessProvisionedClient(
            vpn_client_id=result["vpn_client_id"],
            client_uuid=result["client_uuid"],
            email=result["email"],
            metadata=metadata,
        )

    async def sync_vless_client(
        self,
        *,
        client_uuid: str,
        email: str,
        metadata: dict[str, Any],
        access_expires_at: datetime | None,
    ) -> None:
        await self._ensure_logged_in()
        inbound_id = int(metadata.get("inbound_id") or 0)
        result = await self.client.sync_vless_client_expiry(
            inbound_id=inbound_id,
            client_uuid=client_uuid,
            email=email,
            access_expires_at=access_expires_at,
        )
        resolved_inbound_id = result.get("inbound_id")
        if resolved_inbound_id:
            metadata["inbound_id"] = int(resolved_inbound_id)

    async def delete_vless_client(
        self,
        *,
        client_uuid: str,
        email: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        await self._ensure_logged_in()
        inbound_id = int(metadata.get("inbound_id") or 0)
        return await self.client.delete_vless_client(inbound_id=inbound_id, client_uuid=client_uuid, email=email)

    async def build_vless_metadata(
        self,
        *,
        client_uuid: str,
        email: str,
        country_code: str,
        base_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        await self._ensure_logged_in()
        inbound = await self.client.find_inbound("vless", 443)
        if inbound is None:
            raise ValueError("VLESS inbound on port 443 not found")
        connection_name = build_connection_name(
            country_code=country_code,
            country_name=build_region_snapshot(country_code)["country_name"],
            email=email,
        )
        link = build_vless_link(
            inbound=inbound,
            client_uuid=client_uuid,
            email=email,
            connection_name=connection_name,
            country_code=country_code,
        )
        transport = extract_vless_transport_metadata(inbound)
        return {
            **build_region_snapshot(country_code),
            **(base_metadata or {}),
            "provider_type": self.provider_type,
            "transport": (
                "vless_reality_xhttp"
                if transport["stream_network"] == "xhttp"
                else "vless_reality_grpc"
                if transport["stream_network"] == "grpc"
                else "vless_reality_tcp"
            ),
            "vless_link": link,
            "stream_network": transport["stream_network"],
            "transport_label": transport["transport_label"],
            "stream_path": transport.get("stream_path", ""),
            "stream_host": transport.get("stream_host", ""),
            "stream_mode": transport.get("stream_mode", ""),
            "stream_service_name": transport.get("stream_service_name", ""),
            "stream_authority": transport.get("stream_authority", ""),
            "grpc_service_name": transport.get("stream_service_name", ""),
            "grpc_authority": transport.get("stream_authority", ""),
            "grpc_mode": transport.get("stream_mode", ""),
        }

    async def close(self) -> None:
        await self.client.close()


class XrayCoreProvisioner(VPNProvisioner):
    provider_type = "xray_core"

    def __init__(self, country_code: str) -> None:
        self.country_code = country_code
        self.host = config.xray_core_dk_ssh_host
        self.user = config.xray_core_dk_ssh_user
        self.port = config.xray_core_dk_ssh_port
        self.key_path = config.xray_core_dk_ssh_key_path
        self.known_hosts = config.xray_core_dk_ssh_known_hosts
        self.timeout = config.xray_core_dk_ssh_timeout
        self.config_path = config.xray_core_dk_config_path
        self.meta_path = config.xray_core_dk_meta_path

    async def _ssh_python(self, script: str) -> tuple[int, str]:
        if not self.host:
            raise ValueError("XRAY_CORE_DK_SSH_HOST is not configured")
        if not self.key_path or not self.known_hosts:
            raise ValueError("XRAY core SSH key path or known_hosts is not configured")

        command = [
            "ssh",
            "-i",
            self.key_path,
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={self.known_hosts}",
            "-o",
            f"ConnectTimeout={int(self.timeout)}",
            "-p",
            str(self.port),
            f"{self.user}@{self.host}",
            f"python3 -c {shlex.quote('import sys; exec(sys.stdin.read())')}",
        ]
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await process.communicate(script.encode("utf-8"))
        return process.returncode, stdout.decode("utf-8", errors="ignore").strip()

    async def _load_state(self) -> dict[str, Any]:
        script = f"""
import json
from pathlib import Path

config_path = Path({self.config_path!r})
meta_path = Path({self.meta_path!r})
payload = {{
    "config": json.loads(config_path.read_text(encoding="utf-8")),
    "meta": json.loads(meta_path.read_text(encoding="utf-8")),
}}
print(json.dumps(payload, ensure_ascii=False))
"""
        code, output = await self._ssh_python(script)
        if code != 0:
            raise ValueError(f"Failed to load Denmark Xray state: {output}")
        return json.loads(output)

    async def _save_state(self, config_payload: dict[str, Any]) -> None:
        config_json = json.dumps(config_payload, ensure_ascii=False, indent=2)
        script = f"""
import json
import os
import subprocess
from pathlib import Path

config_path = Path({self.config_path!r})
tmp_path = config_path.with_name(config_path.stem + ".tmp.json")
tmp_path.write_text({config_json!r}, encoding="utf-8")
subprocess.run(['xray', 'run', '-test', '-config', str(tmp_path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
os.replace(tmp_path, config_path)
subprocess.run(["systemctl", "reset-failed", "xray"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
subprocess.run(["systemctl", "restart", "xray"], check=True)
subprocess.run(["systemctl", "is-active", "xray"], check=True, stdout=subprocess.DEVNULL)
print("ok")
"""
        code, output = await self._ssh_python(script)
        if code != 0 or output.strip() != "ok":
            raise ValueError(f"Failed to save Denmark Xray config: {output}")

    def _find_client_inbound(self, config_payload: dict[str, Any]) -> dict[str, Any]:
        for inbound in config_payload.get("inbounds", []):
            if inbound.get("protocol") != "vless":
                continue
            if inbound.get("listen") == "@xhttp-dk":
                return inbound
            stream_settings = inbound.get("streamSettings") or {}
            if str(stream_settings.get("network") or "").strip().lower() == "xhttp":
                return inbound
        raise ValueError("Denmark Xray xhttp inbound not found")

    def _upsert_client(
        self,
        config_payload: dict[str, Any],
        *,
        client_uuid: str,
        email: str,
        enabled: bool,
    ) -> bool:
        inbound = self._find_client_inbound(config_payload)
        settings = inbound.setdefault("settings", {})
        clients = list(settings.get("clients") or [])
        desired_client = {"id": client_uuid, "email": email}
        filtered: list[dict[str, Any]] = []
        inserted = False
        for item in clients:
            matches_client = item.get("id") == client_uuid or item.get("email") == email
            if not matches_client:
                filtered.append(item)
                continue
            if enabled and not inserted:
                filtered.append(desired_client)
                inserted = True
        if enabled:
            if not inserted:
                filtered.append(desired_client)
        settings["clients"] = filtered
        inbound["settings"] = settings
        return filtered != clients

    async def health_check(self) -> bool:
        script = f"""
import subprocess
from pathlib import Path

subprocess.run(['xray', 'run', '-test', '-config', {self.config_path!r}], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
subprocess.run(['systemctl', 'is-active', 'xray'], check=True, stdout=subprocess.DEVNULL)
Path({self.meta_path!r}).read_text(encoding='utf-8')
print('ok')
""".strip()
        code, output = await self._ssh_python(script)
        return code == 0 and output.strip() == "ok"

    async def provision_vless_client(
        self,
        *,
        user_id: int,
        email: str,
        access_expires_at: datetime,
        save_callback,
        country_code: str,
    ) -> VlessProvisionedClient:
        state = await self._load_state()
        config_payload = state["config"]
        client_uuid = str(uuid4())
        changed = self._upsert_client(config_payload, client_uuid=client_uuid, email=email, enabled=True)
        if changed:
            await self._save_state(config_payload)
        try:
            vpn_client = await save_callback(
                user_id=user_id,
                protocol="vless",
                client_uuid=client_uuid,
                email=email,
                xui_client_id=None,
                client_data={"provider_type": self.provider_type},
            )
        except Exception:
            rollback_state = await self._load_state()
            rollback_payload = rollback_state["config"]
            if self._upsert_client(rollback_payload, client_uuid=client_uuid, email=email, enabled=False):
                await self._save_state(rollback_payload)
            raise
        metadata = await self.build_vless_metadata(
            client_uuid=client_uuid,
            email=email,
            country_code=country_code,
            base_metadata={"server_record_id": email},
        )
        return VlessProvisionedClient(
            vpn_client_id=vpn_client.id,
            client_uuid=client_uuid,
            email=email,
            metadata=metadata,
        )

    async def sync_vless_client(
        self,
        *,
        client_uuid: str,
        email: str,
        metadata: dict[str, Any],
        access_expires_at: datetime | None,
    ) -> None:
        state = await self._load_state()
        config_payload = state["config"]
        changed = self._upsert_client(
            config_payload,
            client_uuid=client_uuid,
            email=email,
            enabled=access_expires_at is not None,
        )
        if changed:
            await self._save_state(config_payload)

    async def delete_vless_client(
        self,
        *,
        client_uuid: str,
        email: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        state = await self._load_state()
        config_payload = state["config"]
        changed = self._upsert_client(
            config_payload,
            client_uuid=client_uuid,
            email=email,
            enabled=False,
        )
        if changed:
            await self._save_state(config_payload)
        return {"success": True, "msg": "Deleted from Xray core config", "obj": None}

    async def build_vless_metadata(
        self,
        *,
        client_uuid: str,
        email: str,
        country_code: str,
        base_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = await self._load_state()
        meta = state["meta"]
        normalized_meta = _normalize_xray_core_meta(meta)
        active_profile_name = _resolve_xray_profile_name(normalized_meta, base_metadata)
        active_profile = normalized_meta["profiles"][active_profile_name]
        connection_name = build_connection_name(
            country_code=country_code,
            country_name=build_region_snapshot(country_code)["country_name"],
            email=email,
        )
        region_snapshot = build_region_snapshot(country_code)
        payload = {
            **region_snapshot,
            **(base_metadata or {}),
            "provider_type": self.provider_type,
            "transport": "vless_reality_xhttp",
            **active_profile,
            "active_profile": active_profile_name,
            "connection_profile": active_profile_name,
            "mtu_default": normalized_meta["mtu_default"],
            "mtu_fallback": normalized_meta["mtu_fallback"],
            "compatibility_fallback_region": normalized_meta["compatibility_fallback_region"],
            "dns_servers": normalized_meta["dns_servers"],
        }
        connection_profiles: dict[str, Any] = {}
        for profile_name, profile in normalized_meta["profiles"].items():
            profile_payload = {
                **region_snapshot,
                **profile,
                "profile_name": profile_name,
                "provider_type": self.provider_type,
                "transport": "vless_reality_xhttp",
            }
            profile_payload["vless_link"] = build_vless_link_from_metadata(
                metadata=profile_payload,
                client_uuid=client_uuid,
                email=email,
                connection_name=connection_name,
                country_code=country_code,
            )
            connection_profiles[profile_name] = profile_payload
        payload["connection_profiles"] = connection_profiles
        payload["vless_link"] = connection_profiles[active_profile_name]["vless_link"]
        if "reserve" in connection_profiles:
            payload["reserve_vless_link"] = connection_profiles["reserve"]["vless_link"]
        return payload


class RetiredRegionProvisioner(VPNProvisioner):
    provider_type = "retired"

    def __init__(self, country_code: str) -> None:
        self.country_code = country_code

    def _raise_retired(self) -> None:
        raise ValueError(f"Region `{self.country_code}` has been retired from the product contour")

    async def health_check(self) -> bool:
        return False

    async def provision_vless_client(
        self,
        *,
        user_id: int,
        email: str,
        access_expires_at: datetime,
        save_callback,
        country_code: str,
    ) -> VlessProvisionedClient:
        del user_id, email, access_expires_at, save_callback, country_code
        self._raise_retired()

    async def sync_vless_client(
        self,
        *,
        client_uuid: str,
        email: str,
        metadata: dict[str, Any],
        access_expires_at: datetime | None,
    ) -> None:
        del client_uuid, email, metadata, access_expires_at
        self._raise_retired()

    async def delete_vless_client(
        self,
        *,
        client_uuid: str,
        email: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        del client_uuid, email, metadata
        self._raise_retired()

    async def build_vless_metadata(
        self,
        *,
        client_uuid: str,
        email: str,
        country_code: str,
        base_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del client_uuid, email, country_code, base_metadata
        self._raise_retired()


def get_vless_provisioner(country_code: str | None, provider_type: str | None = None) -> VPNProvisioner:
    resolved_provider = provider_type or get_country_provider_type(country_code)
    if resolved_provider == "xray_core":
        return XrayCoreProvisioner(country_code or "dk")
    if resolved_provider == "retired":
        return RetiredRegionProvisioner(country_code or "ee")
    return XUIProvisioner(country_code or "de")


def region_supports_protocol(country_code: str | None, protocol: str) -> bool:
    provider_type = get_country_provider_type(country_code)
    if provider_type == "retired":
        return False
    if protocol != "vless":
        return provider_type == "xui"
    return True
