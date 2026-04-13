import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

from bot.crypto_pay import CryptoPayClient, CryptoPayError


def main() -> None:
    client = CryptoPayClient(
        api_token="test-token",
        webhook_max_age_seconds=900,
    )

    body = json.dumps(
        {
            "update_type": "invoice_paid",
            "request_date": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "invoice_id": 12345,
                "payload": json.dumps({"type": "subscription", "tariff_code": "1m", "user_id": 7}),
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")

    secret = hashlib.sha256(b"test-token").digest()
    signature = hmac.new(secret, body, hashlib.sha256).hexdigest()

    assert client.verify_webhook_signature(body, signature) is True
    assert client.verify_webhook_signature(body, "bad-signature") is False

    fresh_date = datetime.now(timezone.utc).isoformat()
    stale_date = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    assert client.request_is_fresh(fresh_date) is True
    assert client.request_is_fresh(stale_date) is False

    payload = client.parse_invoice_payload('{"type":"subscription","tariff_code":"1m","user_id":7}')
    assert payload["tariff_code"] == "1m"

    try:
        client.parse_invoice_payload("{broken")
    except CryptoPayError:
        pass
    else:
        raise AssertionError("Invalid payload must raise CryptoPayError")

    print("Crypto Pay tests passed")


if __name__ == "__main__":
    main()
