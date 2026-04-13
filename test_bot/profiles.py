from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bot.utils.vless import build_trojan_link_from_metadata, build_vless_link_from_metadata


@dataclass(frozen=True)
class TestProfile:
    key: str
    title: str
    country_code: str
    platform_label: str
    protocol_label: str
    client_id: str
    connection_name: str
    based_on: str
    metadata: dict
    vpn_client_id: int | None = None
    delivery_kind: str = "uri"
    config_path: str | None = None


TEST_PROFILES: dict[str, TestProfile] = {
    "de_android": TestProfile(
        key="de_android",
        title="Germany Mobile Android",
        country_code="de",
        platform_label="Android",
        protocol_label="VLESS Reality TCP",
        client_id="5a776b54-9d3e-47be-bf23-f33b4ae16d22",
        connection_name="AMONORA-DE-ANDROID-TEST-V2",
        based_on="Germany live 443",
        metadata={
            "port": 9443,
            "stream_network": "tcp",
            "fingerprint": "chrome",
            "reality_server_name": "www.microsoft.com",
            "reality_short_id": "6f1c2a4e9b8d3c70",
            "reality_public_key": "7b340Abf5B3sdmoHzVSDWCaqSJX8_vBqz-63qk0-6Qw",
        },
    ),
    "de_iphone": TestProfile(
        key="de_iphone",
        title="Germany Mobile iPhone",
        country_code="de",
        platform_label="iPhone",
        protocol_label="VLESS Reality TCP",
        client_id="c3b4393d-7bc3-44db-8f9c-d7c137c3c7ba",
        connection_name="AMONORA-DE-IPHONE-TEST-V2",
        based_on="Germany live 443",
        metadata={
            "port": 10443,
            "stream_network": "tcp",
            "fingerprint": "safari",
            "reality_server_name": "www.microsoft.com",
            "reality_short_id": "8b27d1e4c9036af2",
            "reality_public_key": "7b340Abf5B3sdmoHzVSDWCaqSJX8_vBqz-63qk0-6Qw",
        },
    ),
    "dk_android": TestProfile(
        key="dk_android",
        title="Denmark Mobile Android",
        country_code="dk",
        platform_label="Android",
        protocol_label="VLESS Reality XHTTP",
        client_id="d258cf2a-aed3-4dff-8b74-6db8c1855dc5",
        connection_name="AMONORA-DK-ANDROID-TEST-V2",
        based_on="Denmark live primary 443",
        metadata={
            "port": 9443,
            "stream_network": "xhttp",
            "stream_path": "/api/v1/updates",
            "stream_mode": "packet-up",
            "fingerprint": "chrome",
            "reality_server_name": "www.apple.com",
            "reality_short_id": "b7f4c1935e2a6d08",
            "reality_public_key": "ek2qyhS-WjqRUomJezXVGeI-okhCYrHfN3byAmEwlDQ",
            "alpn": ["h3", "h2", "http/1.1"],
        },
    ),
    "dk_iphone": TestProfile(
        key="dk_iphone",
        title="Denmark Mobile iPhone",
        country_code="dk",
        platform_label="iPhone",
        protocol_label="VLESS Reality XHTTP",
        client_id="4bf18d5c-3fe8-4ccf-98b7-baa81d02e21d",
        connection_name="AMONORA-DK-IPHONE-TEST-V2",
        based_on="Denmark live reserve 8443",
        metadata={
            "port": 10443,
            "stream_network": "xhttp",
            "stream_path": "/graphql",
            "stream_mode": "packet-up",
            "fingerprint": "safari",
            "reality_server_name": "www.apple.com",
            "reality_short_id": "d9a2604e7c1b5f83",
            "reality_public_key": "ek2qyhS-WjqRUomJezXVGeI-okhCYrHfN3byAmEwlDQ",
            "alpn": ["h2", "http/1.1"],
        },
    ),
}


def get_test_profiles() -> list[TestProfile]:
    return list(TEST_PROFILES.values())


def get_test_profile(key: str) -> TestProfile | None:
    return TEST_PROFILES.get(key)


def build_test_profile_link(profile: TestProfile) -> str:
    if profile.delivery_kind == "config":
        if not profile.config_path:
            raise ValueError(f"Config path is not set for test profile {profile.key}")
        path = Path(profile.config_path)
        if not path.is_file():
            raise FileNotFoundError(f"Config file not found for test profile {profile.key}: {path}")
        return path.read_text(encoding="utf-8").strip()
    if profile.protocol_label.startswith("Trojan"):
        return build_trojan_link_from_metadata(
            profile.metadata,
            password=profile.client_id,
            email=profile.key,
            connection_name=profile.connection_name,
            country_code=profile.country_code,
        )
    return build_vless_link_from_metadata(
        profile.metadata,
        client_uuid=profile.client_id,
        email=profile.key,
        connection_name=profile.connection_name,
        country_code=profile.country_code,
    )
