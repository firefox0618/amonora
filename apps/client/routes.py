from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse

from bot.public_subscription import (
    bind_public_subscription_request_slot,
    build_public_subscription_feed_url,
    build_public_subscription_happ_wrapper_url,
    build_public_subscription_page_url,
    build_public_subscription_request_context,
    describe_public_subscription_feed_failure,
    extract_public_subscription_token_from_url,
    get_public_subscription_feed_payload,
    get_public_subscription_summary_by_token,
    is_public_subscription_client_request,
    is_valid_public_subscription_token,
    touch_public_subscription_surface,
)

from apps.shared.public_runtime import (
    CLIENT_APP_ASSET_VERSION,
    client_ip,
    is_client_public_host_request,
    plaintext_response_with_headers,
    query_flag,
    render_not_found_page,
    should_render_html_not_found,
    templates,
)


router = APIRouter()


async def public_subscription_feed_response(
    request: Request,
    token: str,
    *,
    force_client_binding: bool,
):
    slot_index: int | None = None
    include_extra = query_flag(request.query_params, "include_extra")
    if force_client_binding or is_public_subscription_client_request(request.headers, query_params=request.query_params):
        request_context = build_public_subscription_request_context(
            headers=request.headers,
            source_ip=client_ip(request),
            query_params=request.query_params,
        )
        binding = await bind_public_subscription_request_slot(token, request_context=request_context)
        if binding is None:
            status_code, message = await describe_public_subscription_feed_failure(token)
            return PlainTextResponse(message, status_code=status_code)
        if str(binding.get("status") or "").strip().lower() == "limit_reached":
            return PlainTextResponse("Device limit reached", status_code=403)
        try:
            slot_index = int(binding.get("slot_index") or 0) or None
        except (TypeError, ValueError):
            return PlainTextResponse("Not Found", status_code=404)

    payload = await get_public_subscription_feed_payload(
        token,
        slot_index=slot_index,
        include_extra=include_extra,
    )
    if payload is None:
        status_code, message = await describe_public_subscription_feed_failure(token, slot_index=slot_index)
        return PlainTextResponse(message, status_code=status_code)
    content, headers = payload
    return plaintext_response_with_headers(content, headers=headers)


@router.get("/api/public/subscriptions/{token}/summary", response_class=JSONResponse)
async def public_subscription_summary(request: Request, token: str):
    if not is_client_public_host_request(request):
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    summary = await get_public_subscription_summary_by_token(token)
    if summary is None:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    return {"ok": True, "subscription": summary}


@router.post("/api/public/subscriptions/{token}/touch", response_class=JSONResponse)
async def public_subscription_touch(request: Request, token: str):
    if not is_client_public_host_request(request):
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    if not is_valid_public_subscription_token(token):
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    touched = await touch_public_subscription_surface(token, feed_access=False)
    if not touched:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    return {"ok": True}


@router.get("/sub/{token}", response_class=PlainTextResponse)
async def public_subscription_feed(request: Request, token: str):
    if not is_client_public_host_request(request):
        return PlainTextResponse("Not Found", status_code=404)
    return await public_subscription_feed_response(request, token, force_client_binding=False)


@router.get("/happ/add", response_class=HTMLResponse)
async def public_subscription_happ_wrapper(request: Request):
    if not is_client_public_host_request(request):
        return PlainTextResponse("Not Found", status_code=404)

    raw_subscription_url = str(request.query_params.get("sub") or "").strip()
    token = extract_public_subscription_token_from_url(raw_subscription_url)
    if token is None:
        return PlainTextResponse("Not Found", status_code=404)

    page_url = build_public_subscription_page_url(token)
    feed_url = build_public_subscription_feed_url(token)
    return templates.TemplateResponse(
        request,
        "client_happ_wrapper.html",
        {
            "request": request,
            "page_title": "Amonora Happ Wrapper",
            "page_description": "Amonora помогает открыть Happ и добавить готовую подписку через собственный безопасный wrapper.",
            "canonical_url": build_public_subscription_happ_wrapper_url(page_url),
            "page_url": page_url,
            "feed_url": feed_url,
            "happ_deep_link": f"happ://add/{feed_url}",
            "asset_version": CLIENT_APP_ASSET_VERSION,
        },
    )


@router.get("/{token}")
async def public_subscription_page(request: Request, token: str):
    if not is_client_public_host_request(request):
        if should_render_html_not_found(request):
            return render_not_found_page(request)
        return PlainTextResponse("Not Found", status_code=404)
    if not is_valid_public_subscription_token(token):
        return PlainTextResponse("Not Found", status_code=404)
    if is_public_subscription_client_request(request.headers, query_params=request.query_params):
        feed_url = build_public_subscription_feed_url(token)
        if query_flag(request.query_params, "include_extra"):
            feed_url = f"{feed_url}?include_extra=1"
        return RedirectResponse(feed_url, status_code=307)
    return templates.TemplateResponse(
        request,
        "client_subscription_shell.html",
        {
            "request": request,
            "page_title": "Amonora",
            "page_description": "Единая ссылка на подписку Amonora.",
            "canonical_url": build_public_subscription_page_url(token),
            "client_token": token,
            "asset_version": CLIENT_APP_ASSET_VERSION,
        },
    )
