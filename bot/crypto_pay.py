import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from bot.config import config


class CryptoPayError(RuntimeError):
    pass


@dataclass(frozen=True)
class CryptoInvoice:
    invoice_id: str
    invoice_hash: str
    pay_url: str
    status: str
    expiration_date: datetime | None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _canonical_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


class CryptoPayClient:
    def __init__(
        self,
        api_token: str | None = None,
        base_url: str | None = None,
        accepted_assets: str | None = None,
        swap_to: str | None = None,
        invoice_expires_seconds: int | None = None,
        webhook_max_age_seconds: int | None = None,
    ) -> None:
        self.api_token = api_token if api_token is not None else config.crypto_pay_api_token
        self.base_url = (base_url if base_url is not None else config.crypto_pay_base_url).rstrip("/")
        self.accepted_assets = accepted_assets if accepted_assets is not None else config.crypto_pay_accepted_assets
        self.swap_to = swap_to if swap_to is not None else config.crypto_pay_swap_to
        self.invoice_expires_seconds = (
            invoice_expires_seconds
            if invoice_expires_seconds is not None
            else config.crypto_pay_invoice_expires_seconds
        )
        self.webhook_max_age_seconds = (
            webhook_max_age_seconds
            if webhook_max_age_seconds is not None
            else config.crypto_pay_webhook_max_age_seconds
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_token)

    @staticmethod
    def canonical_payload(payload: dict[str, Any]) -> str:
        return _canonical_payload(payload)

    def _headers(self) -> dict[str, str]:
        if not self.api_token:
            raise CryptoPayError("Crypto Pay API token is not configured")
        return {"Crypto-Pay-API-Token": self.api_token}

    async def _request(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.post(
                f"{self.base_url}/{method}",
                headers=self._headers(),
                json=payload,
            )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise CryptoPayError(data.get("error", {}).get("name", "Crypto Pay request failed"))
        return data["result"]

    async def create_invoice(self, amount_rub: int, title: str, payload: dict[str, Any]) -> CryptoInvoice:
        request_payload: dict[str, Any] = {
            "currency_type": "fiat",
            "fiat": "RUB",
            "accepted_assets": self.accepted_assets,
            "amount": str(amount_rub),
            "description": title,
            "payload": self.canonical_payload(payload),
            "allow_comments": False,
            "allow_anonymous": True,
            "expires_in": self.invoice_expires_seconds,
            "paid_btn_name": "openBot",
            "paid_btn_url": "https://t.me/amonora_bot",
            "hidden_message": "Оплата получена. Возвращайся в Amonora Bot, доступ обновится автоматически.",
        }
        if self.swap_to:
            request_payload["swap_to"] = self.swap_to

        result = await self._request("createInvoice", request_payload)
        pay_url = (
            result.get("bot_invoice_url")
            or result.get("mini_app_invoice_url")
            or result.get("web_app_invoice_url")
        )
        if not pay_url:
            raise CryptoPayError("Crypto Pay did not return an invoice URL")

        return CryptoInvoice(
            invoice_id=str(result["invoice_id"]),
            invoice_hash=result["hash"],
            pay_url=pay_url,
            status=result.get("status", "active"),
            expiration_date=_parse_datetime(result.get("expiration_date")),
        )

    async def get_invoice(self, invoice_id: str) -> dict[str, Any] | None:
        result = await self._request("getInvoices", {"invoice_ids": invoice_id})
        items = result.get("items") or []
        if not items:
            return None
        return items[0]

    def verify_webhook_signature(self, raw_body: bytes, signature: str | None) -> bool:
        if not self.api_token or not signature:
            return False
        secret = hashlib.sha256(self.api_token.encode("utf-8")).digest()
        expected = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def request_is_fresh(self, request_date: str | None) -> bool:
        parsed = _parse_datetime(request_date)
        if parsed is None:
            return False
        age_seconds = abs((datetime.now(timezone.utc) - parsed).total_seconds())
        return age_seconds <= self.webhook_max_age_seconds

    @staticmethod
    def parse_invoice_payload(invoice_payload: str | None) -> dict[str, Any]:
        if not invoice_payload:
            raise CryptoPayError("Invoice payload is empty")
        try:
            payload = json.loads(invoice_payload)
        except json.JSONDecodeError as exc:
            raise CryptoPayError("Invoice payload is invalid") from exc
        if not isinstance(payload, dict):
            raise CryptoPayError("Invoice payload is not an object")
        return payload
