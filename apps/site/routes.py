import asyncio
from datetime import datetime, timedelta
import hashlib
import hmac
from uuid import uuid4

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse

from backend.core.database import async_session
from bot.config import config
from bot.db import (
    create_landing_bridge_user,
    create_vpn_client,
    delete_landing_bridge_user_if_unused,
    update_vpn_client_metadata,
)
from bot.utils.regions import build_region_snapshot
from bot.vpn_provisioning import get_vless_provisioner

from apps.shared.public_runtime import (
    BRIDGE_ACCESS_COOKIE_NAME,
    BRIDGE_ACCESS_DEVICE_NAME,
    BRIDGE_ACCESS_DURATION_DAYS,
    BRIDGE_ACCESS_RATE_LIMIT_SECONDS,
    BRIDGE_ACCESS_REGION_ORDER,
    PUBLIC_WEB_BASE_URL,
    build_context,
    canonical_public_url,
    client_ip,
    is_client_public_host_request,
    query_flag,
    render_markdown_page,
    render_not_found_page,
    templates,
)


router = APIRouter()

LEGAL_PAGES = {
    "contacts": {
        "title": "Контакты владельца и службы поддержки",
        "slug": "06-юридическое/контакты.md",
        "description": "Публичные контакты владельца сервиса Amonora и каналы для обращений пользователей.",
    },
    "privacy": {
        "title": "Политика обработки персональных данных",
        "slug": "06-юридическое/политика-конфиденциальности.md",
        "description": "Порядок обработки персональных данных пользователей Amonora.",
    },
    "terms": {
        "title": "Оферта / пользовательское соглашение",
        "slug": "06-юридическое/условия-использования.md",
        "description": "Условия использования сайта, Telegram-ботов и цифрового сервиса Amonora.",
    },
    "refunds": {
        "title": "Политика возврата и поддержки",
        "slug": "06-юридическое/возврат-и-поддержка.md",
        "description": "Порядок поддержки, возвратов, спорных оплат и урегулирования обращений.",
    },
    "license": {
        "title": "Лицензия и права на материалы",
        "slug": "06-юридическое/лицензия-и-права-на-материалы.md",
        "description": "Условия использования материалов сайта, текстов, дизайна и программных компонентов Amonora.",
    },
    "cookies": {
        "title": "Политика использования cookie",
        "slug": "06-юридическое/политика-cookie.md",
        "description": "Какие cookie использует Amonora, для чего они нужны и как управлять согласием.",
    },
}

MANUAL_PAGE = {
    "title": "Инструкция для пользователей Amonora",
    "slug": "01-обзор/инструкция-пользователя.md",
    "description": "Пошаговая инструкция для пользователей Amonora: старт, создание устройства, получение ключа, подключение и обращение в поддержку.",
    "eyebrow": "руководство пользователя",
}

VERIFICATION_FILES = {
    "capitalist_15d6b31e67": "38ddac0470",
}

_bridge_issue_timestamps: dict[str, datetime] = {}
_bridge_issue_lock = asyncio.Lock()


def should_redirect_landing(request: Request) -> bool:
    return is_client_public_host_request(request) and request.method in {"GET", "HEAD"}


def bridge_cookie_secret() -> str:
    return str(config.platega_webhook_secret or config.bot_token or "amonora-bridge")


def sign_bridge_cookie(timestamp: int) -> str:
    raw = str(timestamp).encode("utf-8")
    signature = hmac.new(bridge_cookie_secret().encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return f"{timestamp}:{signature}"


def read_bridge_cookie(value: str | None) -> datetime | None:
    if not value or ":" not in value:
        return None
    raw_ts, signature = value.split(":", 1)
    if not raw_ts.isdigit():
        return None
    expected = hmac.new(bridge_cookie_secret().encode("utf-8"), raw_ts.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    return datetime.utcfromtimestamp(int(raw_ts))


def bridge_cookie_retry_at(request: Request) -> datetime | None:
    issued_at = read_bridge_cookie(request.cookies.get(BRIDGE_ACCESS_COOKIE_NAME))
    if issued_at is None:
        return None
    retry_at = issued_at + timedelta(seconds=BRIDGE_ACCESS_RATE_LIMIT_SECONDS)
    if retry_at <= datetime.utcnow():
        return None
    return retry_at


async def consume_bridge_rate_limit(source_ip: str) -> datetime | None:
    if not source_ip:
        return None
    async with _bridge_issue_lock:
        now = datetime.utcnow()
        expired_keys = [
            key
            for key, issued_at in _bridge_issue_timestamps.items()
            if issued_at <= now - timedelta(seconds=BRIDGE_ACCESS_RATE_LIMIT_SECONDS)
        ]
        for key in expired_keys:
            _bridge_issue_timestamps.pop(key, None)

        last_issued_at = _bridge_issue_timestamps.get(source_ip)
        if last_issued_at and last_issued_at > now - timedelta(seconds=BRIDGE_ACCESS_RATE_LIMIT_SECONDS):
            return last_issued_at + timedelta(seconds=BRIDGE_ACCESS_RATE_LIMIT_SECONDS)

        _bridge_issue_timestamps[source_ip] = now
        return None


async def release_bridge_rate_limit(source_ip: str) -> None:
    if not source_ip:
        return
    async with _bridge_issue_lock:
        _bridge_issue_timestamps.pop(source_ip, None)


async def issue_bridge_vless_key(user_id: int, access_expires_at: datetime) -> dict:
    async def check_region(country_code: str) -> tuple[str, bool]:
        provisioner = get_vless_provisioner(country_code)
        try:
            return (country_code, await provisioner.health_check())
        finally:
            await provisioner.close()

    results = await asyncio.gather(*[check_region(cc) for cc in BRIDGE_ACCESS_REGION_ORDER], return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            continue
        country_code, healthy = result
        if not healthy:
            continue

        provisioner = get_vless_provisioner(country_code)
        try:
            email = f"landing_bridge_{user_id}_{uuid4().hex[:10]}"
            provision_result = await provisioner.provision_vless_client(
                user_id=user_id,
                email=email,
                access_expires_at=access_expires_at,
                save_callback=create_vpn_client,
                country_code=country_code,
            )
            metadata = {
                "device_name": BRIDGE_ACCESS_DEVICE_NAME,
                "device_type": "landing_bridge",
                "protocol": "vless",
                "delivery_mode": "landing_bridge",
                "bridge_access": True,
                "bridge_source": "landing",
                "bridge_expires_at": access_expires_at.isoformat(),
                **build_region_snapshot(country_code),
                **provision_result.metadata,
            }
            await update_vpn_client_metadata(provision_result.vpn_client_id, metadata)
            return {
                "country_code": country_code,
                "country_name": metadata["country_name"],
                "metadata": metadata,
            }
        finally:
            await provisioner.close()

    raise RuntimeError("all regions unavailable")


async def check_provisioner_health(country_code: str) -> tuple[str, bool | Exception]:
    try:
        provisioner = get_vless_provisioner(country_code)
        try:
            return (country_code, await provisioner.health_check())
        finally:
            await provisioner.close()
    except Exception as exc:
        return (country_code, exc)


@router.get("/", response_class=HTMLResponse)
async def landing_index(request: Request):
    if should_redirect_landing(request):
        return RedirectResponse(PUBLIC_WEB_BASE_URL, status_code=302)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            **build_context(),
            "canonical_url": canonical_public_url(request),
        },
    )


@router.head("/")
async def landing_head(request: Request):
    if should_redirect_landing(request):
        return RedirectResponse(PUBLIC_WEB_BASE_URL, status_code=302)
    return Response(status_code=200, media_type="text/html")


@router.get("/{filename}.txt", response_class=PlainTextResponse)
async def verification_file(filename: str):
    content = VERIFICATION_FILES.get(filename)
    if content is None:
        return PlainTextResponse("Not Found", status_code=404)
    return PlainTextResponse(content)


@router.get("/legal/{page_key}", response_class=HTMLResponse)
async def legal_page(request: Request, page_key: str):
    page = LEGAL_PAGES.get(page_key)
    if page is None:
        return render_not_found_page(
            request,
            page_title="Документ не найден",
            page_description="Запрошенный юридический документ не найден.",
            page_eyebrow="юридические документы",
            document_description="Такой юридической страницы сейчас нет. Вернитесь на главную страницу и откройте нужный раздел заново.",
        )

    return render_markdown_page(
        request,
        slug=page["slug"],
        page_title=page["title"],
        page_description=page["description"],
        page_eyebrow="юридические документы",
        page_links=[
            {"href": "/legal/contacts", "label": "Контакты"},
            {"href": "/legal/privacy", "label": "ПДн"},
            {"href": "/legal/terms", "label": "Оферта"},
            {"href": "/legal/refunds", "label": "Возвраты и поддержка"},
        ],
    )


@router.get("/manual", response_class=HTMLResponse)
async def manual_page(request: Request):
    if is_client_public_host_request(request):
        return RedirectResponse(f"{PUBLIC_WEB_BASE_URL}/manual", status_code=302)
    return render_markdown_page(
        request,
        slug=MANUAL_PAGE["slug"],
        page_title=MANUAL_PAGE["title"],
        page_description=MANUAL_PAGE["description"],
        page_eyebrow=MANUAL_PAGE["eyebrow"],
    )


@router.get("/health", response_class=JSONResponse)
async def healthcheck():
    checks: dict[str, str | float] = {"service": "amonora-landing"}

    try:
        async with async_session() as session:
            import sqlalchemy as sa

            result = await session.execute(sa.text("SELECT 1"))
            result.scalar()
        checks["db"] = "ok"
    except Exception as exc:
        checks["db"] = str(exc)[:64]

    vpn_checks: list[dict] = []
    results = await asyncio.gather(
        check_provisioner_health("dk"),
        check_provisioner_health("de"),
        return_exceptions=True,
    )
    for country_code, ok in results:
        if isinstance(ok, Exception):
            vpn_checks.append({"region": country_code, "status": f"error: {type(ok).__name__}"})
        else:
            vpn_checks.append({"region": country_code, "status": "ok" if ok else "unhealthy"})
    checks["vpn_regions"] = vpn_checks

    all_ok = checks.get("db") == "ok"
    checks["ok"] = all_ok
    return JSONResponse(checks, status_code=200 if all_ok else 503)


@router.post("/bridge/access", response_class=JSONResponse)
async def bridge_access(request: Request):
    source_ip = client_ip(request)
    cookie_retry_at = bridge_cookie_retry_at(request)
    if cookie_retry_at is not None:
        return JSONResponse(
            {
                "ok": False,
                "error": "bridge_rate_limited",
                "message": "Новый ключ можно запросить немного позже. Текущий лимит: один мостовой ключ на IP раз в 30 минут.",
                "retry_at": cookie_retry_at.isoformat(),
            },
            status_code=429,
            headers={"Cache-Control": "no-store"},
        )

    retry_at = await consume_bridge_rate_limit(source_ip)
    if retry_at is not None:
        return JSONResponse(
            {
                "ok": False,
                "error": "bridge_rate_limited",
                "message": "Новый ключ можно запросить немного позже. Текущий лимит: один мостовой ключ на IP раз в 30 минут.",
                "retry_at": retry_at.isoformat(),
            },
            status_code=429,
            headers={"Cache-Control": "no-store"},
        )

    user = None
    try:
        user = await create_landing_bridge_user(duration_days=BRIDGE_ACCESS_DURATION_DAYS)
        access_expires_at = user.subscription_expires_at
        if access_expires_at is None:
            raise ValueError("bridge access expiration missing")
        payload = await issue_bridge_vless_key(user.id, access_expires_at)
    except Exception:
        await release_bridge_rate_limit(source_ip)
        if user is not None:
            await delete_landing_bridge_user_if_unused(user.id)
        return JSONResponse(
            {
                "ok": False,
                "error": "bridge_access_unavailable",
                "message": "Сейчас не удалось подготовить временный ключ. Попробуй ещё раз чуть позже.",
            },
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )

    expires_text = access_expires_at.strftime("%Y-%m-%d %H:%M:%S")
    response = JSONResponse(
        {
            "ok": True,
            "data": {
                "device_name": BRIDGE_ACCESS_DEVICE_NAME,
                "country_name": payload["country_name"],
                "access_expires_at": expires_text,
                "vless_link": payload["metadata"]["vless_link"],
                "manual_url": "/manual",
                "bot_url": "https://t.me/amonora_bot",
            },
        },
        headers={"Cache-Control": "no-store"},
    )
    response.set_cookie(
        BRIDGE_ACCESS_COOKIE_NAME,
        sign_bridge_cookie(int(datetime.utcnow().timestamp())),
        max_age=BRIDGE_ACCESS_RATE_LIMIT_SECONDS,
        httponly=True,
        secure=True,
        samesite="Lax",
    )
    return response
