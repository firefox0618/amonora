import json
import logging
from copy import deepcopy
from datetime import datetime
import ipaddress
import re
from urllib.parse import quote
from uuid import uuid4

import httpx

from bot.config import config
from bot.utils.regions import get_country_panel_url


logger = logging.getLogger(__name__)
XUI_MAX_DEVICES_PER_KEY = max(int(config.vpn_max_devices_per_key or 1), 1)
XUI_SINGLE_DEVICE_LIMIT_IP = XUI_MAX_DEVICES_PER_KEY


def _resolve_country_panel_credentials(country_code: str | None) -> tuple[str, str]:
    normalized_country = str(country_code or "").strip().lower()
    if normalized_country == "ee":
        username = str(config.xui_username_ee or config.xui_username or "").strip()
        password = str(config.xui_password_ee or config.xui_password or "").strip()
        return username, password
    if normalized_country == "fr":
        username = str(config.xui_username_fr or config.xui_username or "").strip()
        password = str(config.xui_password_fr or config.xui_password or "").strip()
        return username, password
    return config.xui_username, config.xui_password


def _json_dict(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


class XUIClient:
    def __init__(
        self,
        country_code: str | None = None,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        resolved_base_url = base_url or get_country_panel_url(country_code)
        if not resolved_base_url:
            raise ValueError(f"No x-ui panel URL configured for country_code={country_code}")
        self.base_url = resolved_base_url.rstrip("/")
        resolved_username, resolved_password = _resolve_country_panel_credentials(country_code)
        self.username = username or resolved_username
        self.password = password or resolved_password
        self.country_code = country_code
        self.client = httpx.AsyncClient(follow_redirects=True, timeout=15.0)
        self._csrf_token: str | None = None
        self._base_path: str = ""

    @staticmethod
    def _normalize_base_path(value: str | None) -> str:
        raw_value = str(value or "").strip()
        if not raw_value or raw_value == "/":
            return ""
        normalized = f"/{raw_value.strip('/')}"
        return normalized

    @staticmethod
    def _extract_meta_content(html: str, name: str) -> str | None:
        pattern = rf'<meta\s+name="{re.escape(name)}"\s+content="([^"]*)"'
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if not match:
            return None
        value = str(match.group(1) or "").strip()
        return value or None

    async def _prime_login_context(self) -> None:
        try:
            response = await self.client.get(self.base_url)
            response.raise_for_status()
        except httpx.HTTPError:
            self._csrf_token = None
            self._base_path = ""
            return

        html = response.text
        self._csrf_token = self._extract_meta_content(html, "csrf-token")
        self._base_path = self._normalize_base_path(self._extract_meta_content(html, "base-path"))

    def _build_client_settings(
        self,
        *,
        protocol: str,
        client_uuid: str,
        email: str,
        expiry_time_ms: int,
        enable: bool = True,
        flow: str = "",
    ) -> dict:
        client: dict[str, object] = {
            "email": email,
            "limitIp": XUI_MAX_DEVICES_PER_KEY,
            "totalGB": 0,
            "expiryTime": expiry_time_ms,
            "enable": enable,
            "tgId": 0,
            "subId": "",
            "comment": "",
            "reset": 0,
        }
        if protocol == "vless":
            client["id"] = client_uuid
            client["flow"] = flow
        elif protocol == "trojan":
            client["password"] = client_uuid
        else:
            raise ValueError(f"Unsupported client protocol: {protocol}")

        return {"clients": [client]}

    async def login(self) -> bool:
        self._csrf_token = None
        self._base_path = ""
        self.client.headers.pop("X-CSRF-Token", None)
        self.client.headers.pop("Referer", None)
        await self._prime_login_context()
        headers: dict[str, str] = {}
        if self._csrf_token:
            headers["X-CSRF-Token"] = self._csrf_token
        if self._base_path:
            headers["Referer"] = f"{self.base_url}{self._base_path}/"
        response = await self.client.post(
            f"{self.base_url}/login",
            headers=headers,
            data={"username": self.username, "password": self.password},
        )
        if response.status_code == 200:
            if self._csrf_token:
                self.client.headers["X-CSRF-Token"] = self._csrf_token
            if self._base_path:
                self.client.headers["Referer"] = f"{self.base_url}{self._base_path}/"
        return response.status_code == 200

    async def get_inbounds(self) -> dict:
        response = await self.client.get(f"{self.base_url}/panel/api/inbounds/list")
        response.raise_for_status()
        return response.json()

    async def find_inbound(self, protocol: str, port: int | None = None) -> dict | None:
        data = await self.get_inbounds()
        if not data.get("success"):
            return None

        for inbound in data.get("obj", []):
            if inbound.get("protocol") != protocol:
                continue
            if port is not None and inbound.get("port") != port:
                continue
            return inbound

        return None

    async def list_inbounds(self, protocol: str | None = None) -> list[dict]:
        data = await self.get_inbounds()
        if not data.get("success"):
            return []
        inbounds = data.get("obj", [])
        if protocol is None:
            return inbounds
        return [inbound for inbound in inbounds if inbound.get("protocol") == protocol]

    @staticmethod
    def _normalize_client_ips(obj: object) -> list[str]:
        candidates: list[str] = []
        if isinstance(obj, str):
            raw = obj.strip()
            if not raw or raw.lower() == "no ip record":
                return []
            separators = raw.replace("\n", ",").split(",")
            candidates = [item.strip() for item in separators if item.strip()]
        elif isinstance(obj, list):
            candidates = [str(item).strip() for item in obj if str(item).strip()]
        elif isinstance(obj, dict):
            for key in ("ips", "ipList", "items"):
                value = obj.get(key)
                if isinstance(value, list):
                    candidates.extend(str(item).strip() for item in value if str(item).strip())
                elif isinstance(value, str):
                    candidates.extend(item.strip() for item in value.replace("\n", ",").split(",") if item.strip())
        valid_ips: list[str] = []
        for value in candidates:
            try:
                ipaddress.ip_address(value)
            except ValueError:
                continue
            if value not in valid_ips:
                valid_ips.append(value)
        return valid_ips

    async def get_client_ips(self, email: str) -> list[str]:
        response = await self.client.post(
            f"{self.base_url}/panel/api/inbounds/clientIps/{quote(email, safe='')}",
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            return []
        return self._normalize_client_ips(payload.get("obj"))

    def _client_matches(self, protocol: str, client: dict, client_uuid: str, email: str) -> bool:
        if protocol == "trojan":
            return client.get("password") == client_uuid or client.get("email") == email
        return client.get("id") == client_uuid or client.get("email") == email

    async def resolve_client_inbound_id(
        self,
        protocol: str,
        client_uuid: str,
        email: str,
        inbound_id: int | None = None,
    ) -> int | None:
        inbounds = await self.list_inbounds(protocol)
        if not inbounds:
            return None

        preferred_inbound_id = int(inbound_id or 0)
        ordered_inbounds = sorted(
            inbounds,
            key=lambda inbound: 0 if preferred_inbound_id and inbound.get("id") == preferred_inbound_id else 1,
        )

        for inbound in ordered_inbounds:
            settings = _json_dict(inbound.get("settings"))
            clients = settings.get("clients", [])
            if any(self._client_matches(protocol, client, client_uuid, email) for client in clients):
                resolved = inbound.get("id")
                return int(resolved) if resolved is not None else None
        return None

    async def add_vless_client(
        self,
        inbound_id: int,
        email: str,
        client_uuid: str,
        expiry_time_ms: int,
    ) -> dict:
        payload = {
            "id": inbound_id,
            "settings": json.dumps(
                self._build_client_settings(
                    protocol="vless",
                    client_uuid=client_uuid,
                    email=email,
                    expiry_time_ms=expiry_time_ms,
                )
            ),
        }

        try:
            response = await self.client.post(
                f"{self.base_url}/panel/api/inbounds/addClient",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
        return await self._add_client_via_clients_api(
            protocol="vless",
            inbound_id=inbound_id,
            email=email,
            client_uuid=client_uuid,
            expiry_time_ms=expiry_time_ms,
        )

    async def add_trojan_client(
        self,
        inbound_id: int,
        email: str,
        password: str,
        expiry_time_ms: int,
    ) -> dict:
        payload = {
            "id": inbound_id,
            "settings": json.dumps(
                self._build_client_settings(
                    protocol="trojan",
                    client_uuid=password,
                    email=email,
                    expiry_time_ms=expiry_time_ms,
                )
            ),
        }

        try:
            response = await self.client.post(
                f"{self.base_url}/panel/api/inbounds/addClient",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
        return await self._add_client_via_clients_api(
            protocol="trojan",
            inbound_id=inbound_id,
            email=email,
            client_uuid=password,
            expiry_time_ms=expiry_time_ms,
        )

    async def update_vless_client(
        self,
        inbound_id: int,
        client_uuid: str,
        email: str,
        expiry_time_ms: int,
        enable: bool = True,
    ) -> dict:
        payload = {
            "id": inbound_id,
            "settings": json.dumps(
                self._build_client_settings(
                    protocol="vless",
                    client_uuid=client_uuid,
                    email=email,
                    expiry_time_ms=expiry_time_ms,
                    enable=enable,
                )
            ),
        }

        try:
            response = await self.client.post(
                f"{self.base_url}/panel/api/inbounds/updateClient/{quote(client_uuid, safe='')}",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
        return await self._update_client_via_clients_api(
            protocol="vless",
            email=email,
            client_uuid=client_uuid,
            expiry_time_ms=expiry_time_ms,
            enable=enable,
        )

    def _build_clients_api_client_payload(
        self,
        *,
        protocol: str,
        email: str,
        client_uuid: str,
        expiry_time_ms: int,
        enable: bool = True,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "email": email,
            "subId": "",
            "totalGB": 0,
            "expiryTime": expiry_time_ms,
            "limitIp": XUI_MAX_DEVICES_PER_KEY,
            "tgId": 0,
            "comment": "",
            "enable": enable,
        }
        if protocol == "vless":
            payload["id"] = client_uuid
            payload["flow"] = ""
        elif protocol == "trojan":
            payload["password"] = client_uuid
        else:
            raise ValueError(f"Unsupported client protocol: {protocol}")
        return payload

    async def _add_client_via_clients_api(
        self,
        *,
        protocol: str,
        inbound_id: int,
        email: str,
        client_uuid: str,
        expiry_time_ms: int,
    ) -> dict:
        payload = {
            "client": self._build_clients_api_client_payload(
                protocol=protocol,
                email=email,
                client_uuid=client_uuid,
                expiry_time_ms=expiry_time_ms,
                enable=True,
            ),
            "inboundIds": [int(inbound_id)],
        }
        response = await self.client.post(
            f"{self.base_url}/panel/api/clients/add",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def _update_client_via_clients_api(
        self,
        *,
        protocol: str,
        email: str,
        client_uuid: str,
        expiry_time_ms: int,
        enable: bool,
    ) -> dict:
        payload = self._build_clients_api_client_payload(
            protocol=protocol,
            email=email,
            client_uuid=client_uuid,
            expiry_time_ms=expiry_time_ms,
            enable=enable,
        )
        response = await self.client.post(
            f"{self.base_url}/panel/api/clients/update/{quote(email, safe='')}",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def _delete_client_via_clients_api(self, *, email: str) -> dict:
        response = await self.client.post(
            f"{self.base_url}/panel/api/clients/del/{quote(email, safe='')}",
        )
        response.raise_for_status()
        return response.json()

    async def provision_trojan_client(
        self,
        user_id: int,
        email: str,
        access_expires_at: datetime,
        save_callback,
    ) -> dict:
        inbound = await self.find_inbound("trojan", 8443)
        if inbound is None:
            raise ValueError("Trojan inbound on port 8443 not found")

        password = str(uuid4())
        expiry_time_ms = int(access_expires_at.timestamp() * 1000)
        result = await self.add_trojan_client(
            inbound_id=inbound["id"],
            email=email,
            password=password,
            expiry_time_ms=expiry_time_ms,
        )
        if not result.get("success"):
            raise ValueError("3x-ui failed to create Trojan client")

        try:
            vpn_client = await save_callback(
                user_id=user_id,
                protocol="trojan",
                client_uuid=password,
                email=email,
                xui_client_id=password,
                client_data={"inbound_id": inbound["id"]},
            )
        except Exception:
            logger.exception("Failed to save Trojan client in DB, rolling back panel state")
            await self.delete_trojan_client(inbound["id"], password, email=email)
            raise

        return {
            "inbound_id": inbound["id"],
            "client_uuid": password,
            "email": email,
            "vpn_client_id": vpn_client.id,
        }

    def _build_inbound_update_payload(self, inbound: dict, settings: dict) -> dict:
        payload = {
            "up": inbound.get("up", 0),
            "down": inbound.get("down", 0),
            "total": inbound.get("total", 0),
            "remark": inbound.get("remark", ""),
            "enable": inbound.get("enable", True),
            "expiryTime": inbound.get("expiryTime", 0),
            "trafficReset": inbound.get("trafficReset", ""),
            "lastTrafficResetTime": inbound.get("lastTrafficResetTime", 0),
            "listen": inbound.get("listen", ""),
            "port": inbound.get("port"),
            "protocol": inbound.get("protocol"),
            "settings": json.dumps(settings, ensure_ascii=False, indent=2),
            "sniffing": inbound.get("sniffing", "{}"),
        }

        stream_settings = inbound.get("streamSettings")
        if stream_settings:
            payload["streamSettings"] = stream_settings

        return payload

    async def update_inbound_settings(self, inbound: dict, settings: dict) -> dict:
        payload = self._build_inbound_update_payload(inbound, settings)
        response = await self.client.post(
            f"{self.base_url}/panel/api/inbounds/update/{inbound['id']}",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def provision_vless_client(
        self,
        user_id: int,
        email: str,
        access_expires_at: datetime,
        save_callback,
    ) -> dict:
        inbound = await self.find_inbound("vless", 443)
        if inbound is None:
            raise ValueError("VLESS inbound on port 443 not found")

        client_uuid = str(uuid4())
        expiry_time_ms = int(access_expires_at.timestamp() * 1000)
        result = await self.add_vless_client(
            inbound_id=inbound["id"],
            email=email,
            client_uuid=client_uuid,
            expiry_time_ms=expiry_time_ms,
        )
        if not result.get("success"):
            raise ValueError("3x-ui failed to create VLESS client")

        try:
            vpn_client = await save_callback(
                user_id=user_id,
                protocol="vless",
                client_uuid=client_uuid,
                email=email,
                xui_client_id=client_uuid,
                client_data={"inbound_id": inbound["id"]},
            )
        except Exception:
            logger.exception("Failed to save VLESS client in DB, rolling back panel state")
            await self.delete_vless_client(inbound["id"], client_uuid, email=email)
            raise

        return {
            "inbound_id": inbound["id"],
            "client_uuid": client_uuid,
            "email": email,
            "vpn_client_id": vpn_client.id,
        }

    async def sync_vless_client_expiry(
        self,
        inbound_id: int,
        client_uuid: str,
        email: str,
        access_expires_at: datetime | None,
    ) -> dict:
        resolved_inbound_id = await self.resolve_client_inbound_id("vless", client_uuid, email, inbound_id)
        if resolved_inbound_id is None:
            if access_expires_at is None:
                return {
                    "success": True,
                    "msg": "VLESS client already absent.",
                    "obj": None,
                    "inbound_id": int(inbound_id or 0) or None,
                    "recreated": False,
                }
            inbound = await self.find_inbound("vless", 443)
            if inbound is None:
                raise ValueError("VLESS inbound on port 443 not found")
            expiry_time_ms = int(access_expires_at.timestamp() * 1000)
            created = await self.add_vless_client(
                inbound_id=int(inbound["id"]),
                email=email,
                client_uuid=client_uuid,
                expiry_time_ms=expiry_time_ms,
            )
            return {
                **created,
                "inbound_id": int(inbound["id"]),
                "recreated": True,
            }
        expiry_time_ms = int(access_expires_at.timestamp() * 1000) if access_expires_at else 0
        result = await self.update_vless_client(
            inbound_id=resolved_inbound_id,
            client_uuid=client_uuid,
            email=email,
            expiry_time_ms=expiry_time_ms,
            enable=access_expires_at is not None,
        )
        result["inbound_id"] = int(resolved_inbound_id)
        result["recreated"] = False
        return result

    async def sync_trojan_client_expiry(
        self,
        inbound_id: int,
        client_uuid: str,
        email: str,
        access_expires_at: datetime | None,
    ) -> dict:
        trojan_inbounds = await self.list_inbounds("trojan")
        if not trojan_inbounds:
            if access_expires_at is None:
                return {
                    "success": True,
                    "msg": "Trojan client already absent.",
                    "obj": None,
                    "inbound_id": int(inbound_id or 0) or None,
                    "recreated": False,
                }
            raise ValueError("Trojan inbound not found")

        ordered_inbounds = sorted(
            trojan_inbounds,
            key=lambda inbound: 0 if inbound.get("id") == inbound_id else 1,
        )

        for inbound in ordered_inbounds:
            settings = _json_dict(inbound.get("settings"))
            clients = deepcopy(settings.get("clients", []))
            updated = False

            for client in clients:
                if client.get("password") != client_uuid and client.get("email") != email:
                    continue
                client["enable"] = access_expires_at is not None
                client["expiryTime"] = int(access_expires_at.timestamp() * 1000) if access_expires_at else 0
                client["limitIp"] = XUI_MAX_DEVICES_PER_KEY
                updated = True
                break

            if not updated:
                continue

            settings["clients"] = clients
            result = await self.update_inbound_settings(inbound, settings)
            result["inbound_id"] = int(inbound.get("id")) if inbound.get("id") is not None else None
            result["recreated"] = False
            return result

        if access_expires_at is None:
            return {
                "success": True,
                "msg": "Trojan client already absent.",
                "obj": None,
                "inbound_id": int(inbound_id or 0) or None,
                "recreated": False,
            }

        inbound = await self.find_inbound("trojan", 8443)
        if inbound is None:
            raise ValueError("Trojan inbound not found")
        expiry_time_ms = int(access_expires_at.timestamp() * 1000)
        created = await self.add_trojan_client(
            inbound_id=int(inbound["id"]),
            email=email,
            password=client_uuid,
            expiry_time_ms=expiry_time_ms,
        )
        return {
            **created,
            "inbound_id": int(inbound["id"]),
            "recreated": True,
        }

    async def delete_vless_client(
        self,
        inbound_id: int,
        client_uuid: str,
        email: str | None = None,
    ) -> dict:
        result = {"success": False, "msg": "client lookup fallback used", "obj": None}
        if inbound_id:
            try:
                response = await self.client.post(
                    f"{self.base_url}/panel/api/inbounds/{inbound_id}/delClient/{quote(client_uuid, safe='')}"
                )
                response.raise_for_status()
                result = response.json()
                if result.get("success"):
                    return result
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 404:
                    raise
                if email:
                    return await self._delete_client_via_clients_api(email=email)

        vless_inbounds = await self.list_inbounds("vless")
        if not vless_inbounds:
            return {
                "success": True,
                "msg": "VLESS inbound already absent.",
                "obj": None,
            }

        ordered_inbounds = sorted(
            vless_inbounds,
            key=lambda inbound: 0 if inbound.get("id") == inbound_id else 1,
        )

        for inbound in ordered_inbounds:
            settings = _json_dict(inbound.get("settings"))
            clients = settings.get("clients", [])
            filtered_clients = [
                client
                for client in clients
                if client.get("id") != client_uuid
                and (email is None or client.get("email") != email)
            ]
            if len(filtered_clients) == len(clients):
                continue

            settings["clients"] = filtered_clients
            return await self.update_inbound_settings(inbound, settings)

        return result

    async def delete_trojan_client(
        self,
        inbound_id: int,
        client_uuid: str,
        email: str | None = None,
    ) -> dict:
        if email:
            try:
                return await self._delete_client_via_clients_api(email=email)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 404:
                    raise
        trojan_inbounds = await self.list_inbounds("trojan")
        if not trojan_inbounds:
            return {
                "success": True,
                "msg": "Trojan inbound already absent.",
                "obj": None,
            }

        ordered_inbounds = sorted(
            trojan_inbounds,
            key=lambda inbound: 0 if inbound.get("id") == inbound_id else 1,
        )

        for inbound in ordered_inbounds:
            settings = _json_dict(inbound.get("settings"))
            clients = settings.get("clients", [])
            filtered_clients = [
                client
                for client in clients
                if client.get("password") != client_uuid
                and (email is None or client.get("email") != email)
            ]
            if len(filtered_clients) == len(clients):
                continue

            settings["clients"] = filtered_clients
            return await self.update_inbound_settings(inbound, settings)

        return {
            "success": True,
            "msg": "Trojan client already absent.",
            "obj": None,
        }

    async def close(self) -> None:
        await self.client.aclose()
