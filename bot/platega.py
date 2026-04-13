import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from bot.config import config


class PlategaError(RuntimeError):
    pass


@dataclass(frozen=True)
class PlategaPayment:
    transaction_id: str
    checkout_url: str
    status: str
    payment_method_id: int | str
    expires_in: str | None
    raw: dict[str, Any]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class PlategaClient:
    METHOD_SBP_QR = 2
    METHOD_CRYPTO = 13

    STATUS_PENDING = "PENDING"
    STATUS_CONFIRMED = "CONFIRMED"
    STATUS_CANCELED = "CANCELED"
    STATUS_CHARGEBACKED = "CHARGEBACKED"

    def __init__(
        self,
        merchant_id: str | None = None,
        secret_key: str | None = None,
        base_url: str | None = None,
        webhook_max_age_seconds: int | None = None,
    ) -> None:
        self.merchant_id = merchant_id if merchant_id is not None else config.platega_merchant_id
        self.secret_key = secret_key if secret_key is not None else config.platega_secret_key
        self.base_url = (base_url if base_url is not None else config.platega_base_url).rstrip("/")
        self.webhook_max_age_seconds = (
            int(webhook_max_age_seconds)
            if webhook_max_age_seconds is not None
            else int(config.platega_callback_max_age_seconds)
        )

    @property
    def configured(self) -> bool:
        return bool(self.merchant_id and self.secret_key)

    def _headers(self) -> dict[str, str]:
        if not self.configured:
            raise PlategaError("Platega merchant credentials are not configured")
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-MerchantId": str(self.merchant_id),
            "X-Secret": str(self.secret_key),
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        json_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.request(
                method,
                f"{self.base_url}{endpoint}",
                headers=self._headers(),
                json=json_payload,
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            try:
                details = response.json()
            except ValueError:
                details = response.text
            raise PlategaError(f"Platega request failed: {details}") from exc

        try:
            return response.json()
        except ValueError as exc:
            raise PlategaError("Platega returned invalid JSON") from exc

    async def create_payment(
        self,
        *,
        amount_rub: int,
        payment_method_id: int,
        description: str,
        payload: dict[str, Any],
        return_url: str | None = None,
        failed_url: str | None = None,
    ) -> PlategaPayment:
        response = await self._request(
            "POST",
            "/transaction/process",
            json_payload={
                "paymentMethod": int(payment_method_id),
                "paymentDetails": {
                    "amount": float(amount_rub),
                    "currency": "RUB",
                },
                "description": description,
                "payload": json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                **({"return": return_url} if return_url else {}),
                **({"failedUrl": failed_url} if failed_url else {}),
            },
        )
        transaction_id = str(response.get("transactionId") or "").strip()
        checkout_url = str(response.get("redirect") or "").strip()
        if not transaction_id or not checkout_url:
            raise PlategaError("Platega did not return transactionId or redirect URL")
        return PlategaPayment(
            transaction_id=transaction_id,
            checkout_url=checkout_url,
            status=str(response.get("status") or self.STATUS_PENDING),
            payment_method_id=response.get("paymentMethod") or payment_method_id,
            expires_in=str(response.get("expiresIn") or "") or None,
            raw=response,
        )

    async def get_payment_status(self, transaction_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/transaction/{transaction_id}")

    def validate_callback(self, *, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        if not self.configured:
            raise PlategaError("Platega merchant credentials are not configured")
        normalized_headers = {key.lower(): value for key, value in headers.items()}
        merchant_id = normalized_headers.get("x-merchantid") or normalized_headers.get("x-merchant-id")
        secret = normalized_headers.get("x-secret")
        if merchant_id != self.merchant_id:
            raise PlategaError("Invalid or missing X-MerchantId header")
        if secret != self.secret_key:
            raise PlategaError("Invalid or missing X-Secret header")
        if not body:
            raise PlategaError("Empty callback body")
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PlategaError("Invalid callback JSON") from exc
        required_fields = {"id", "status", "paymentMethod"}
        missing = [field for field in required_fields if field not in payload]
        if missing:
            raise PlategaError(f"Missing callback fields: {', '.join(missing)}")
        callback_timestamp = self._extract_callback_timestamp(payload)
        if callback_timestamp is not None:
            now_utc = datetime.now(timezone.utc)
            age_seconds = (now_utc - callback_timestamp).total_seconds()
            if age_seconds > self.webhook_max_age_seconds:
                raise PlategaError("Callback payload is too old")
            if age_seconds < -300:
                raise PlategaError("Callback payload timestamp is in the future")
        payload["_callback_hash"] = hashlib.sha256(body).hexdigest()
        return payload

    @staticmethod
    def _parse_callback_timestamp(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            raw_value = float(value)
            if raw_value > 10_000_000_000:
                raw_value /= 1000.0
            return datetime.fromtimestamp(raw_value, tz=timezone.utc)
        normalized = str(value or "").strip()
        if not normalized:
            return None
        if normalized.isdigit():
            return PlategaClient._parse_callback_timestamp(int(normalized))
        try:
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @classmethod
    def _extract_callback_timestamp(cls, payload: dict[str, Any]) -> datetime | None:
        for key in ("timestamp", "updatedAt", "updated_at", "createdAt", "created_at"):
            parsed = cls._parse_callback_timestamp(payload.get(key))
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def parse_payload(raw_payload: str | None) -> dict[str, Any]:
        if not raw_payload:
            raise PlategaError("Payment payload is empty")
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            raise PlategaError("Payment payload is invalid") from exc
        if not isinstance(payload, dict):
            raise PlategaError("Payment payload is not an object")
        return payload

    @staticmethod
    def now_sync_stamp() -> str:
        return _utcnow_iso()
