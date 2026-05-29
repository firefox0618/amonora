import json
from urllib.parse import quote

from bot.utils.regions import get_country_import_name, get_country_vpn_host


def build_connection_name(
    country_code: str | None = None,
    country_name: str | None = None,
    email: str | None = None,
) -> str:
    if country_code:
        return get_country_import_name(country_code)

    if country_name and country_name.strip():
        normalized_name = country_name.strip().lower()
        if "эстон" in normalized_name:
            return get_country_import_name("ee")
        if "дан" in normalized_name:
            return get_country_import_name("dk")
        if "герман" in normalized_name:
            return get_country_import_name("de")
        if "нидерланд" in normalized_name:
            return get_country_import_name("de")

    if email:
        return f"AMONORA-{email.upper()}"

    return "AMONORA"


def build_vless_link(
    inbound: dict,
    client_uuid: str,
    email: str,
    connection_name: str | None = None,
    country_code: str | None = None,
) -> str:
    stream_settings = _json_object(inbound.get("streamSettings"))
    inbound_settings = _json_object(inbound.get("settings"))
    transport = extract_vless_transport_metadata(inbound)

    reality_settings = stream_settings["realitySettings"]
    reality_extra = reality_settings["settings"]

    public_key = reality_extra["publicKey"]
    fingerprint = reality_extra.get("fingerprint", "chrome")
    server_name = reality_settings["serverNames"][0]
    short_id = reality_settings["shortIds"][0]
    spider_x = reality_extra.get("spiderX", "/")
    # For standard client import, VLESS links should keep `encryption=none`.
    # 3x-ui may expose panel-side PQ metadata here, but pushing that value into
    # the share link breaks compatibility for regular mobile/desktop clients.
    encryption = "none"

    flow = ""
    for client in inbound_settings.get("clients", []):
        if client.get("id") == client_uuid or client.get("email") == email:
            flow = client.get("flow") or ""
            break

    name = quote(connection_name or build_connection_name(email=email))
    spider_x_encoded = quote(spider_x, safe="")

    query_parts = [
        f"type={quote(transport['stream_network'], safe='')}",
        "security=reality",
        f"encryption={quote(encryption, safe='')}",
        f"pbk={public_key}",
        f"fp={fingerprint}",
        f"sni={server_name}",
        f"sid={short_id}",
        f"spx={spider_x_encoded}",
    ]
    if transport["stream_network"] == "tcp":
        query_parts.append("headerType=none")
    if transport["stream_network"] == "grpc":
        query_parts.append(f"serviceName={quote(transport.get('stream_service_name', ''), safe='')}")
        query_parts.append(f"mode={quote(transport.get('stream_mode') or 'gun', safe='')}")
        if transport.get("stream_authority"):
            query_parts.append(f"authority={quote(transport['stream_authority'], safe='')}")
    if transport.get("stream_path"):
        query_parts.append(f"path={quote(transport['stream_path'], safe='')}")
    if transport.get("stream_host"):
        query_parts.append(f"host={quote(transport['stream_host'], safe='')}")
    if transport.get("stream_mode") and transport["stream_network"] != "grpc":
        query_parts.append(f"mode={quote(transport['stream_mode'], safe='')}")
    if flow:
        query_parts.append(f"flow={quote(flow, safe='')}")

    return (
        f"vless://{client_uuid}@{get_country_vpn_host(country_code)}:{inbound['port']}"
        f"?{'&'.join(query_parts)}"
        f"#{name}"
    )


def build_trojan_link(
    inbound: dict,
    password: str,
    email: str,
    connection_name: str | None = None,
    country_code: str | None = None,
) -> str:
    stream_settings = _json_object(inbound.get("streamSettings"))
    tls_settings = stream_settings.get("tlsSettings", {})

    server_name = tls_settings.get("serverName") or get_country_vpn_host(country_code)
    alpn_values = tls_settings.get("alpn") or []
    alpn = quote(",".join(alpn_values), safe="") if alpn_values else ""

    name = quote(connection_name or build_connection_name(email=email))
    query_parts = [
        "security=tls",
        "type=tcp",
        f"sni={quote(server_name, safe='')}",
    ]
    if alpn:
        query_parts.append(f"alpn={alpn}")

    return (
        f"trojan://{quote(password, safe='')}@{get_country_vpn_host(country_code)}:{inbound['port']}"
        f"?{'&'.join(query_parts)}"
        f"#{name}"
    )


def build_trojan_link_from_metadata(
    metadata: dict,
    password: str,
    email: str,
    connection_name: str | None = None,
    country_code: str | None = None,
) -> str:
    server_name = str(metadata.get("server_name") or metadata.get("sni") or get_country_vpn_host(country_code)).strip()
    alpn = _normalize_alpn(metadata.get("alpn"))

    name = quote(connection_name or build_connection_name(country_code=country_code, email=email))
    query_parts = [
        "security=tls",
        "type=tcp",
        f"sni={quote(server_name, safe='')}",
    ]
    if alpn:
        query_parts.append(f"alpn={quote(alpn, safe='')}")

    port = int(metadata.get("port") or 443)
    return (
        f"trojan://{quote(password, safe='')}@{get_country_vpn_host(country_code)}:{port}"
        f"?{'&'.join(query_parts)}"
        f"#{name}"
    )


def build_vless_link_from_metadata(
    metadata: dict,
    client_uuid: str,
    email: str,
    connection_name: str | None = None,
    country_code: str | None = None,
) -> str:
    stream_network = str(metadata.get("stream_network") or "tcp").strip().lower() or "tcp"
    encryption = "none"
    name = quote(connection_name or build_connection_name(country_code=country_code, email=email))
    query_parts = [
        f"type={quote(stream_network, safe='')}",
        "security=reality",
        f"encryption={quote(encryption, safe='')}",
        f"fp={quote(str(metadata.get('fingerprint') or 'chrome'), safe='')}",
        f"sni={quote(str(metadata.get('reality_server_name') or metadata.get('server_name') or get_country_vpn_host(country_code)), safe='')}",
        f"sid={quote(str(metadata.get('reality_short_id') or ''), safe='')}",
    ]

    reality_public_key = str(metadata.get("reality_public_key") or metadata.get("reality_password") or "").strip()
    if reality_public_key:
        query_parts.append(f"pbk={quote(reality_public_key, safe='')}")

    stream_path = _normalize_path(metadata.get("xhttp_path") or metadata.get("stream_path"))
    if stream_network == "tcp":
        query_parts.append("headerType=none")
    if stream_network == "grpc":
        service_name = str(
            metadata.get("grpc_service_name")
            or metadata.get("service_name")
            or metadata.get("stream_service_name")
            or ""
        ).strip()
        if service_name:
            query_parts.append(f"serviceName={quote(service_name, safe='')}")
        query_parts.append(f"mode={quote(str(metadata.get('grpc_mode') or metadata.get('stream_mode') or 'gun'), safe='')}")
        authority = str(metadata.get("grpc_authority") or metadata.get("stream_authority") or "").strip()
        if authority:
            query_parts.append(f"authority={quote(authority, safe='')}")
    alpn = _normalize_alpn(metadata.get("alpn"))
    if alpn:
        query_parts.append(f"alpn={quote(alpn, safe='')}")
    if stream_path:
        query_parts.append(f"path={quote(stream_path, safe='')}")
    if metadata.get("stream_host"):
        query_parts.append(f"host={quote(str(metadata.get('stream_host')), safe='')}")
    if metadata.get("stream_mode") and stream_network != "grpc":
        query_parts.append(f"mode={quote(str(metadata.get('stream_mode')), safe='')}")

    try:
        port = int(metadata.get("port") or 443)
    except (TypeError, ValueError):
        port = 443
    return (
        f"vless://{client_uuid}@{get_country_vpn_host(country_code)}:{port}"
        f"?{'&'.join(query_parts)}"
        f"#{name}"
    )


def extract_vless_transport_metadata(inbound: dict) -> dict[str, str]:
    stream_settings = _json_object(inbound.get("streamSettings"))
    stream_network = str(stream_settings.get("network") or "tcp").strip().lower() or "tcp"
    stream_path = ""
    stream_host = ""
    stream_mode = ""
    stream_service_name = ""
    stream_authority = ""

    if stream_network == "xhttp":
        xhttp_settings = stream_settings.get("xhttpSettings") or {}
        stream_path = _normalize_path(xhttp_settings.get("path"))
        if not stream_path and isinstance(xhttp_settings.get("host"), list):
            hosts = [str(item).strip() for item in xhttp_settings.get("host", []) if str(item).strip()]
            if hosts:
                stream_host = ",".join(hosts)
        elif xhttp_settings.get("host"):
            stream_host = str(xhttp_settings.get("host")).strip()
        stream_mode = str(xhttp_settings.get("mode") or "").strip()
    elif stream_network == "grpc":
        grpc_settings = stream_settings.get("grpcSettings") or {}
        stream_service_name = str(grpc_settings.get("serviceName") or "").strip()
        stream_authority = str(grpc_settings.get("authority") or "").strip()
        stream_mode = "gun"

    return {
        "stream_network": stream_network,
        "transport_label": "gRPC" if stream_network == "grpc" else stream_network.upper() if stream_network else "TCP",
        "stream_path": stream_path,
        "stream_host": stream_host,
        "stream_mode": stream_mode,
        "stream_service_name": stream_service_name,
        "stream_authority": stream_authority,
    }


def _normalize_path(value: object) -> str:
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    if raw.startswith("/"):
        return raw
    return f"/{raw}"


def _json_object(value: object) -> dict:
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


def _normalize_alpn(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        values = [str(item).strip() for item in value if str(item).strip()]
        return ",".join(values)
    return str(value).strip()
