import json
from dataclasses import dataclass


SPLIT_DIRECT_DOMAINS = (
    "geosite:category-ru",
    "geosite:yandex",
    "geosite:vk",
    "domain:gosuslugi.ru",
    "domain:nalog.gov.ru",
)
SPLIT_DIRECT_IPS = (
    "geoip:ru",
    "geoip:private",
)
BLOCKED_PROTOCOLS = ("bittorrent",)


@dataclass(frozen=True)
class RoutingPackSpec:
    key: str
    target_client: str
    filename: str
    preferred_region: str
    fallback_region: str
    dns_mode: str
    client_family: str | None = None
    tun_mtu: int | None = None


CLIENT_ROUTING_PACKS: dict[str, RoutingPackSpec] = {
    "v2rayng": RoutingPackSpec(
        key="v2rayng",
        target_client="v2rayNG",
        filename="amonora_v2rayng_split_routing.json",
        preferred_region="dk",
        fallback_region="de",
        dns_mode="local-for-direct-remote-for-proxy",
    ),
    "nekoray": RoutingPackSpec(
        key="nekoray",
        target_client="Nekoray",
        client_family="xray-or-sing-box",
        filename="amonora_nekoray_split_routing.json",
        preferred_region="dk",
        fallback_region="de",
        dns_mode="direct-domestic-remote-global",
        tun_mtu=1400,
    ),
    "streisand": RoutingPackSpec(
        key="streisand",
        target_client="Streisand",
        client_family="sing-box-oriented",
        filename="amonora_streisand_split_routing.json",
        preferred_region="dk",
        fallback_region="de",
        dns_mode="direct-domestic-remote-global",
    ),
}


def build_split_routing_rules() -> dict:
    return {
        "domainStrategy": "IPIfNonMatch",
        "rules": [
            {
                "type": "field",
                "domain": list(SPLIT_DIRECT_DOMAINS),
                "outboundTag": "direct",
            },
            {
                "type": "field",
                "ip": list(SPLIT_DIRECT_IPS),
                "outboundTag": "direct",
            },
            {
                "type": "field",
                "protocol": list(BLOCKED_PROTOCOLS),
                "outboundTag": "blocked",
            },
            {
                "type": "field",
                "network": "tcp,udp",
                "outboundTag": "proxy",
            },
        ],
    }


def build_full_tunnel_routing_rules() -> dict:
    return {
        "domainStrategy": "IPIfNonMatch",
        "rules": [
            {
                "type": "field",
                "ip": ["geoip:private"],
                "outboundTag": "direct",
            },
            {
                "type": "field",
                "protocol": list(BLOCKED_PROTOCOLS),
                "outboundTag": "blocked",
            },
            {
                "type": "field",
                "network": "tcp,udp",
                "outboundTag": "proxy",
            },
        ],
    }


def _routing_policy(mode: str) -> dict:
    policy = {
        "mode": mode,
        "blocked_protocols": list(BLOCKED_PROTOCOLS),
        "default_outbound": "proxy",
    }
    if mode == "split-tunnel":
        policy["direct_domains"] = list(SPLIT_DIRECT_DOMAINS)
        policy["direct_ips"] = list(SPLIT_DIRECT_IPS)
    return policy


def build_split_routing_pack(spec: RoutingPackSpec) -> dict:
    payload = {
        "schema_version": 2,
        "pack_type": "routing-policy",
        "target_client": spec.target_client,
        "name": "Amonora - Russia Direct Split Tunnel",
        "preferred_region": spec.preferred_region,
        "fallback_region": spec.fallback_region,
        "dns": {
            "mode": spec.dns_mode,
            "upstreams": [
                "https+local://cloudflare-dns.com/dns-query",
                "https+local://dns.sb/dns-query",
            ],
        },
        "policy": _routing_policy("split-tunnel"),
        "routing": build_split_routing_rules(),
    }
    if spec.client_family:
        payload["client_family"] = spec.client_family
    if spec.tun_mtu is not None:
        payload["tun"] = {"mtu": spec.tun_mtu, "fallback_mtu": 1420}
    else:
        payload["mtu"] = {"default": 1400, "fallback": 1420}
    return payload


def build_full_tunnel_pack(spec: RoutingPackSpec) -> dict:
    payload = {
        "schema_version": 2,
        "pack_type": "routing-policy",
        "target_client": spec.target_client,
        "name": "Amonora - Full Tunnel Fallback",
        "preferred_region": "de",
        "fallback_region": "de",
        "dns": {
            "mode": "remote-for-all",
            "upstreams": [
                "https+local://cloudflare-dns.com/dns-query",
                "https+local://dns.sb/dns-query",
            ],
        },
        "policy": _routing_policy("full-tunnel"),
        "routing": build_full_tunnel_routing_rules(),
    }
    if spec.client_family:
        payload["client_family"] = spec.client_family
    if spec.tun_mtu is not None:
        payload["tun"] = {"mtu": spec.tun_mtu, "fallback_mtu": 1420}
    else:
        payload["mtu"] = {"default": 1400, "fallback": 1420}
    return payload


def get_pack_spec_for_device(os_type: str) -> RoutingPackSpec:
    normalized = (os_type or "").lower()
    if normalized in {"android", "tv"}:
        return CLIENT_ROUTING_PACKS["v2rayng"]
    if normalized in {"ios", "macos"}:
        return CLIENT_ROUTING_PACKS["streisand"]
    return CLIENT_ROUTING_PACKS["nekoray"]


def build_split_routing_pack_for_device(os_type: str) -> tuple[RoutingPackSpec, dict]:
    spec = get_pack_spec_for_device(os_type)
    return spec, build_split_routing_pack(spec)


def dumps_pack(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
