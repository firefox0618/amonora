import json

import uvicorn
from aiogram import Bot
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from apps.client.routes import router as client_router
from apps.shared.public_runtime import CLIENT_STATIC_DIR, SITE_STATIC_DIR, lifespan, setup_common_public_app
from apps.site.routes import router as site_router
from bot.config import config
from bot.crypto_pay import CryptoPayClient, CryptoPayError
from bot.db import (
    confirm_external_payment_record,
    create_external_payment_record,
    get_payment_record_by_external_id,
    payment_record_effect_applied,
)
from bot.payment_flow import finalize_subscription_payment, notify_payment_success, notify_referral_bonus
from bot.platega import PlategaClient, PlategaError
from bot.platega_flow import handle_platega_callback_payload
from bot.utils.tariffs import get_tariff
from dashboard.finance import sync_income_entry_for_payment_record


app = FastAPI(
    title="Amonora",
    description="Public landing for the Amonora ecosystem.",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=str(SITE_STATIC_DIR)), name="static")
app.mount("/client-static", StaticFiles(directory=str(CLIENT_STATIC_DIR), check_dir=False), name="client-static")
setup_common_public_app(app, redirect_public_hosts=True)
app.include_router(site_router)
app.include_router(client_router)

crypto_pay_client = CryptoPayClient()
platega_client = PlategaClient()


@app.post("/vpn/activate", response_class=JSONResponse)
async def vpn_activate():
    return JSONResponse(
        {
            "ok": False,
            "status": "gone",
            "message": "Legacy Estonia activation path has been retired.",
        },
        status_code=410,
        headers={"Cache-Control": "no-store"},
    )


@app.post("/webhooks/crypto-pay/{secret}", response_class=JSONResponse)
async def crypto_pay_webhook(request: Request, secret: str):
    if not config.enable_legacy_crypto_pay_webhook:
        return JSONResponse({"ok": False, "error": "legacy crypto pay webhook disabled"}, status_code=410)
    expected_secret = (config.crypto_pay_webhook_secret or "").strip()
    if not expected_secret or secret != expected_secret:
        return JSONResponse({"ok": False, "error": "invalid secret"}, status_code=404)
    if not crypto_pay_client.configured:
        return JSONResponse({"ok": False, "error": "crypto pay disabled"}, status_code=503)

    raw_body = await request.body()
    signature = request.headers.get("crypto-pay-api-signature")
    if not crypto_pay_client.verify_webhook_signature(raw_body, signature):
        return JSONResponse({"ok": False, "error": "invalid signature"}, status_code=401)

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JSONResponse({"ok": False, "error": "invalid json"}, status_code=400)

    if not crypto_pay_client.request_is_fresh(payload.get("request_date")):
        return JSONResponse({"ok": False, "error": "stale request"}, status_code=400)

    if payload.get("update_type") != "invoice_paid":
        return JSONResponse({"ok": True, "ignored": True})

    invoice = payload.get("payload") or {}
    invoice_id = str(invoice.get("invoice_id") or "")
    if not invoice_id:
        return JSONResponse({"ok": False, "error": "invoice id missing"}, status_code=400)

    try:
        invoice_payload = crypto_pay_client.parse_invoice_payload(invoice.get("payload"))
    except CryptoPayError:
        return JSONResponse({"ok": False, "error": "invalid invoice payload"}, status_code=400)

    tariff = get_tariff(invoice_payload.get("tariff_code", ""))
    if tariff is None:
        return JSONResponse({"ok": False, "error": "tariff not found"}, status_code=400)

    record = await get_payment_record_by_external_id("crypto_bot", invoice_id)
    if record is None:
        record = await create_external_payment_record(
            user_id=invoice_payload.get("user_id"),
            external_payment_id=invoice_id,
            tariff_code=tariff.code,
            payment_method="crypto_bot",
            amount=tariff.rub_price,
            currency=invoice.get("fiat", "RUB"),
            duration_days=tariff.duration_days,
            note=json.dumps(invoice, ensure_ascii=False),
        )

    record, just_confirmed = await confirm_external_payment_record(
        payment_method="crypto_bot",
        external_payment_id=invoice_id,
        note=json.dumps(invoice, ensure_ascii=False),
    )
    if record is None:
        return JSONResponse({"ok": False, "error": "payment record missing"}, status_code=500)
    if not just_confirmed and payment_record_effect_applied(record):
        return JSONResponse({"ok": True, "duplicate": True})
    if record.user_id is None:
        return JSONResponse({"ok": False, "error": "user missing"}, status_code=400)

    await sync_income_entry_for_payment_record(record.id)

    result = await finalize_subscription_payment(
        user_id=record.user_id,
        tariff_code=record.tariff_code or tariff.code,
        payment_id=record.external_payment_id or invoice_id,
        payment_source="crypto_bot",
        payment_record_id=record.id,
    )
    if result is None:
        return JSONResponse({"ok": False, "error": "activation failed"}, status_code=500)

    telegram_id = result["user"].telegram_id
    bot = Bot(config.bot_token)
    try:
        await notify_payment_success(
            bot=bot,
            telegram_id=telegram_id,
            tariff_title=result["tariff"].title,
            expires_text=result["expires_text"],
            sync_failed=result["sync_failed"],
        )
        await notify_referral_bonus(bot, record.user_id)
    finally:
        await bot.session.close()

    return JSONResponse({"ok": True})


@app.post("/webhooks/platega/{secret}", response_class=JSONResponse)
async def platega_webhook(request: Request, secret: str):
    expected_secret = (config.platega_webhook_secret or "").strip()
    if not expected_secret or secret != expected_secret:
        return JSONResponse({"ok": False, "error": "invalid secret"}, status_code=404)
    if not platega_client.configured:
        return JSONResponse({"ok": False, "error": "platega disabled"}, status_code=503)

    raw_body = await request.body()
    try:
        payload = platega_client.validate_callback(headers=dict(request.headers), body=raw_body)
    except PlategaError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=401)
    except Exception:
        return JSONResponse({"ok": False, "error": "provider_unavailable"}, status_code=502)

    bot = Bot(config.bot_token)
    try:
        result = await handle_platega_callback_payload(payload, notify_user=True, bot=bot)
    except PlategaError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    except Exception:
        return JSONResponse({"ok": False, "error": "provider_unavailable"}, status_code=502)
    finally:
        await bot.session.close()

    record = result["record"]
    response_payload = {
        "ok": True,
        "record_id": record.id,
        "payment_status": record.payment_status,
        "provider_status": result["provider_status"],
    }
    if result["just_confirmed"]:
        response_payload["confirmed"] = True
    if result["provider_sync_problem"]:
        response_payload["provider_sync_problem"] = result["provider_sync_problem"]
    return JSONResponse(response_payload)


def main() -> None:
    uvicorn.run(
        "landing.main:app",
        host="127.0.0.1",
        port=8090,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
