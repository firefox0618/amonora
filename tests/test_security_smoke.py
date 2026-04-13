import tempfile
from pathlib import Path

from bot.utils.texts import (
    active_access_text,
    ask_device_country_text,
    device_card_text,
    renamed_device_text,
    vpn_client_created_text,
)
from support_bot import storage


def test_html_escaping() -> None:
    payload = "<b>owned</b>&\"'"
    rendered = [
        active_access_text(payload, payload),
        ask_device_country_text(payload, "android", "vless"),
        device_card_text({"device_name": payload, "protocol": "vless", "device_type": "android"}, payload),
        renamed_device_text(payload),
        vpn_client_created_text(payload, payload, payload, payload, payload),
    ]
    joined = "\n".join(rendered)
    assert "<b>owned</b>" not in joined
    assert "&lt;b&gt;owned&lt;/b&gt;" in joined


def test_vpn_client_created_text_explains_what_to_copy() -> None:
    rendered = vpn_client_created_text("Устройство", "Стабильный", "Германия", "2026-04-06", "vless://example")
    assert "Что копировать" in rendered
    assert "всю строку целиком" in rendered


def test_corrupted_support_storage() -> None:
    original_dir = storage.STORAGE_DIR
    original_file = storage.STORAGE_FILE

    with tempfile.TemporaryDirectory() as tmpdir:
        storage.STORAGE_DIR = Path(tmpdir)
        storage.STORAGE_FILE = storage.STORAGE_DIR / "support_tickets.json"
        storage.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        storage.STORAGE_FILE.write_text("{not-json", encoding="utf-8")

        data = storage._read_data()
        assert data == {"tickets": {}}
        backups = list(storage.STORAGE_DIR.glob("support_tickets.corrupt-*.json"))
        assert backups

    storage.STORAGE_DIR = original_dir
    storage.STORAGE_FILE = original_file


if __name__ == "__main__":
    test_html_escaping()
    test_corrupted_support_storage()
    print("Security smoke tests passed")
