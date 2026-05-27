from contextlib import asynccontextmanager
import asyncio
from datetime import datetime, timedelta
import functools
import hashlib
import hmac
import json
import logging
from pathlib import Path
from uuid import uuid4

import markdown
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from aiogram import Bot
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.core.database import async_session
from backend.core.tracing import reset_current_trace_id, set_current_trace_id
from bot.config import config
from bot.crypto_pay import CryptoPayClient, CryptoPayError
from bot.db import (
    confirm_external_payment_record,
    create_external_payment_record,
    create_landing_bridge_user,
    create_vpn_client,
    delete_landing_bridge_user_if_unused,
    get_payment_record_by_external_id,
    payment_record_effect_applied,
    update_vpn_client_metadata,
)
from bot.payment_flow import finalize_subscription_payment, notify_payment_success, notify_referral_bonus
from bot.public_subscription import (
    bind_public_subscription_request_slot,
    build_public_subscription_feed_url,
    build_public_subscription_happ_wrapper_url,
    describe_public_subscription_feed_failure,
    build_public_subscription_request_context,
    build_public_subscription_page_url,
    extract_public_subscription_token_from_url,
    get_public_subscription_feed_payload,
    get_public_subscription_summary_by_token,
    is_public_subscription_client_host,
    is_public_subscription_client_request,
    is_valid_public_subscription_token,
    touch_public_subscription_surface,
)
from bot.platega import PlategaClient, PlategaError
from bot.platega_flow import handle_platega_callback_payload
from bot.utils.regions import build_region_snapshot
from bot.utils.tariffs import get_tariff, get_tariffs_list
from bot.utils.logging_setup import configure_logging
from bot.vpn_provisioning import get_vless_provisioner
from dashboard.finance import sync_income_entry_for_payment_record


BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR.parent / "docs"
CLIENT_APP_STATIC_DIR = BASE_DIR / "static" / "client-app"
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

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
BRIDGE_ACCESS_DURATION_DAYS = 1
BRIDGE_ACCESS_REGION_ORDER = ("dk", "de")
BRIDGE_ACCESS_RATE_LIMIT_SECONDS = 30 * 60
BRIDGE_ACCESS_DEVICE_NAME = "Amonora Bridge"
BRIDGE_ACCESS_COOKIE_NAME = "amonora_bridge_cooldown"
PUBLIC_WEB_BASE_URL = config.public_site_base_url.rstrip("/")
PUBLIC_WEB_CANONICAL_HOST = config.public_site_host
PUBLIC_WEB_ALLOWED_HOSTS = frozenset(config.public_site_hosts)
PUBLIC_API_BASE_URL = config.public_api_base_url.rstrip("/")
PUBLIC_API_ALLOWED_HOSTS = frozenset(config.public_api_hosts)
CLIENT_APP_ASSET_VERSION = "20260515-client-domain-v6"
_bridge_issue_timestamps: dict[str, datetime] = {}
_bridge_issue_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    yield


app = FastAPI(
    title="Amonora",
    description="Public landing for the Amonora ecosystem.",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/client-static", StaticFiles(directory=str(CLIENT_APP_STATIC_DIR), check_dir=False), name="client-static")
crypto_pay_client = CryptoPayClient()
platega_client = PlategaClient()


@functools.cache
def build_context() -> dict:
    tariff_notes = {
        "1m": "Быстрый старт",
        "3m": "Оптимальный выбор",
        "6m": "Долгий горизонт",
        "12m": "Максимум спокойствия",
    }
    asset_version = "20260411-sakura-landing-v10"
    tariffs = [
        {
            "code": tariff.code,
            "title": tariff.title,
            "price": f"{tariff.rub_price} ₽",
            "duration": f"{tariff.duration_days} дней доступа",
            "note": tariff_notes.get(tariff.code, "План доступа"),
            "featured": tariff.code == "3m",
        }
        for tariff in get_tariffs_list()
    ]

    return {
        "year": datetime.now().year,
        "brand": "Amonora",
        "product_name": "Amonora",
        "public_web_base_url": PUBLIC_WEB_BASE_URL,
        "og_image_url": _public_static_url("og-image.png"),
        "asset_version": asset_version,
        "owner_name": "Иван Сергеевич Ковалёв",
        "support_email": "amonoraconnect@yandex.ru",
        "support_email_href": "mailto:amonoraconnect@yandex.ru",
        "bot_url": "https://t.me/amonora_bot",
        "channel_url": "https://t.me/amonora_new",
        "support_url": "https://t.me/amonora_support_bot",
        "legal_links": {
            "contacts": "/legal/contacts",
            "privacy": "/legal/privacy",
            "terms": "/legal/terms",
            "refunds": "/legal/refunds",
            "license": "/legal/license",
            "cookies": "/legal/cookies",
        },
        "network_phrase": "AMONORA NETWORK • PRIVATE • FAST • GLOBAL • TELEGRAM CONTROL •",
        "hero": {
            "kicker": "AMONORA",
            "title": "Частная сеть экосистемы Amonora.",
            "text": "Подключай устройство, получай готовый маршрут и управляй доступом через Telegram и веб-интерфейсы сервиса.",
            "primary_label": "Открыть Amonora Bot",
            "secondary_label": "Открыть канал",
        },
        "bridge_access": {
            "eyebrow": "amonora",
            "title": "Ключ на день",
            "text": (
                "Amonora выдаёт временный ключ на 24 часа, чтобы ты смог открыть Telegram, "
                "зайти в @amonora_bot и продолжить весь основной сценарий уже внутри продукта."
            ),
            "story": (
                "Это не отдельный сайт для разовой выдачи конфигов. "
                "Лендинг показывает сам продукт: быстрый вход, инструкции, доступ к Telegram и переход "
                "в основную точку управления Amonora."
            ),
            "steps": [
                {
                    "title": "Получить временный ключ",
                    "text": "Сайт создаёт бесплатный доступ на 1 день без оплаты прямо на сайте.",
                },
                {
                    "title": "Открыть Telegram и бота",
                    "text": "Подключись, зайди в @amonora_bot и активируй пробный период после подписки на канал.",
                },
                {
                    "title": "Продолжить уже внутри Amonora",
                    "text": "Покупка, устройства, инструкции и дальнейшее управление остаются в экосистеме Amonora.",
                },
            ],
            "cta_label": "Получить ключ на 1 день",
            "note": "Бесплатно, без оплаты на сайте. Ключ нужен только как мост до Telegram и бота.",
        },
        "hero_chips": [
            "Germany",
            "Denmark",
            "Telegram control",
            "Private network",
        ],
        "essence_cards": [
            {
                "title": "Telegram-first",
                "text": "Устройства и доступ управляются прямо из Telegram.",
            },
            {
                "title": "Private network",
                "text": "Защищённый маршрут без перегруженного интерфейса.",
            },
            {
                "title": "Amonora ecosystem",
                "text": "Единая точка входа, подключения и управления доступом.",
            },
        ],
        "auto_connect": {
            "eyebrow": "automatic connection system",
            "title": "Автоматическая система подключения",
            "text": "Быстрый, чистый и понятный сценарий: устройство, маршрут, подключение.",
            "signals": ["BOT SIGNAL", "AUTO ROUTE", "READY PROFILE"],
        },
        "locations_head": {
            "eyebrow": "network locations",
            "title": "Две активные точки сети",
            "text": "Germany и Denmark доступны как основные публичные маршруты.",
        },
        "locations": [
            {
                "flag": "DE",
                "emoji": "🇩🇪",
                "name": "Германия",
                "city": "Франкфурт-на-Майне",
                "text": "Мощный ежедневный маршрут для работы, связи и стабильного доступа.",
            },
            {
                "flag": "DK",
                "emoji": "🇩🇰",
                "name": "Дания",
                "city": "Тендер",
                "text": "Быстрый северный маршрут с очень ровным откликом и спокойной сетью.",
            },
        ],
        "tariffs_head": {
            "eyebrow": "access plans",
            "title": "Тарифы",
            "text": "Текущие планы доступа активируются прямо в Telegram и сразу готовы к подключению.",
        },
        "tariffs": tariffs,
        "faq_head": {
            "eyebrow": "quick answers",
            "title": "FAQ",
            "text": "Короткие ответы на главные вопросы перед подключением.",
        },
        "faqs": [
            {
                "title": "Как быстро подключиться?",
                "text": "Открой бота, получи единую ссылку и добавь её в Happ автоматически или вставь вручную.",
            },
            {
                "title": "Какие локации доступны?",
                "text": "Основные публичные маршруты сейчас находятся в Германии и Дании.",
            },
            {
                "title": "Нужен ли отдельный кабинет?",
                "text": "Нет. Управление доступом, устройствами и продлением идёт через Telegram.",
            },
            {
                "title": "Что делать, если что-то не работает?",
                "text": "Напиши на email поддержки, и мы поможем проверить ключ, маршрут и приложение.",
            },
        ],
        "final_cta": {
            "eyebrow": "ready to connect",
            "title": "Запусти Amonora за пару минут",
            "text": "Открой бота, добавь устройство и подключись к сети Amonora.",
        },
        "footer_note": "Amonora — частная цифровая сеть экосистемы.",
    }


def _request_host(request: Request) -> str:
    return request.headers.get("host", "").split(":", 1)[0].strip().lower()


def _is_client_public_host(request: Request) -> bool:
    return is_public_subscription_client_host(_request_host(request))


def _canonical_public_url(request: Request) -> str:
    path = request.url.path or "/"
    query = f"?{request.url.query}" if request.url.query else ""
    return f"{PUBLIC_WEB_BASE_URL}{path}{query}"


def _public_static_url(path: str) -> str:
    """Return canonical /static/ URL for the primary public site host."""
    return f"{PUBLIC_WEB_BASE_URL}/static/{path.lstrip('/')}"


def _should_redirect_public_request(request: Request) -> bool:
    if request.method not in {"GET", "HEAD"}:
        return False
    request_host = _request_host(request)
    if request_host not in PUBLIC_WEB_ALLOWED_HOSTS or request_host == PUBLIC_WEB_CANONICAL_HOST:
        return False
    path = request.url.path or "/"
    return path == "/" or path == "/manual" or path.startswith("/legal/")


@app.middleware("http")
async def canonical_public_host_middleware(request: Request, call_next):
    if _should_redirect_public_request(request):
        return RedirectResponse(_canonical_public_url(request), status_code=308)
    return await call_next(request)


_LANDING_LOGGER = logging.getLogger("landing")


# ─── Security headers ─────────────────────────────────────────────────────────

# ─── Global exception handler ─────────────────────────────────────────────────

SAFE_ERROR_MESSAGE = "Внутренняя ошибка сервера. Попробуйте обновить страницу."
SAFE_ERROR_HTML = (
    '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
    '<title>Ошибка</title></head><body style="font-family:sans-serif;padding:2rem;text-align:center">'
    f"<h1>Ошибка</h1><p>{SAFE_ERROR_MESSAGE}</p></body></html>"
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    _LANDING_LOGGER.exception(
        "Unhandled exception",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "client_ip": _client_ip(request),
            "exc_type": type(exc).__name__,
            "exc_message": str(exc),
        },
    )
    accept = str(request.headers.get("accept", "")).lower()
    if "application/json" in accept or request.url.path.startswith("/api/") or request.url.path.startswith("/webhooks/"):
        return JSONResponse(
            {"ok": False, "error": "internal_server_error", "message": SAFE_ERROR_MESSAGE},
            status_code=500,
        )
    return HTMLResponse(SAFE_ERROR_HTML, status_code=500)


@app.middleware("http")
async def landing_request_id_middleware(request: Request, call_next):
    raw_request_id = str(request.headers.get("x-request-id") or "").strip()
    request_id = (raw_request_id[:64] if raw_request_id else uuid4().hex)
    request.state.request_id = request_id
    token = set_current_trace_id(request_id)
    try:
        response = await call_next(request)
    finally:
        reset_current_trace_id(token)
    response.headers.setdefault("X-Request-ID", request_id)
    return response


@app.middleware("http")
async def static_cache_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path.startswith("/client-static/"):
        response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
    return response


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded.strip():
        return forwarded.split(",", 1)[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _render_markdown_template(
    request: Request,
    *,
    page_title: str,
    page_description: str,
    page_eyebrow: str,
    document_html: str,
    page_links: list[dict[str, str]] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "legal.html",
        {
            **build_context(),
            "canonical_url": _canonical_public_url(request),
            "page_title": page_title,
            "page_description": page_description,
            "page_eyebrow": page_eyebrow,
            "page_links": page_links or [],
            "document_html": document_html,
        },
        status_code=status_code,
    )


def _resolve_docs_page(slug: str) -> Path | None:
    candidate = (DOCS_DIR / slug).resolve()
    try:
        candidate.relative_to(DOCS_DIR.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _not_found_document_html(
    *,
    title: str,
    description: str,
    home_href: str = "/",
) -> str:
    return (
        '<section class="error-404" aria-labelledby="error-404-title">'
        '<span class="error-404__code">404</span>'
        f'<h2 class="error-404__title" id="error-404-title">{title}</h2>'
        f'<p class="error-404__text">{description}</p>'
        f'<a href="{home_href}" class="button button-primary error-404__action">На главную</a>'
        "</section>"
    )


def _render_not_found_page(
    request: Request,
    *,
    page_title: str = "Страница не найдена",
    page_description: str = "Страница не найдена или недоступна.",
    page_eyebrow: str = "ошибка навигации",
    document_title: str = "Страница не найдена или недоступна",
    document_description: str = "Проверь адрес страницы или вернись на главную, чтобы продолжить навигацию по Amonora.",
) -> HTMLResponse:
    return _render_markdown_template(
        request,
        page_title=page_title,
        page_description=page_description,
        page_eyebrow=page_eyebrow,
        document_html=_not_found_document_html(
            title=document_title,
            description=document_description,
        ),
        status_code=404,
    )


def _should_render_html_not_found(request: Request) -> bool:
    path = request.url.path or "/"
    if path.startswith("/static/") or path.startswith("/client-static/"):
        return False
    if path.startswith("/api/") or path.startswith("/webhooks/"):
        return False
    if Path(path).suffix.lower() in {
        ".css",
        ".gif",
        ".ico",
        ".jpeg",
        ".jpg",
        ".js",
        ".json",
        ".map",
        ".png",
        ".svg",
        ".txt",
        ".webp",
    }:
        return False
    accept = str(request.headers.get("accept") or "").lower()
    if "text/html" in accept:
        return True
    if "*/*" in accept and request.method in {"GET", "HEAD"}:
        return True
    return False


@app.exception_handler(404)
async def global_not_found_handler(request: Request, _: StarletteHTTPException):
    if not _should_render_html_not_found(request):
        return PlainTextResponse("Not Found", status_code=404)
    return _render_not_found_page(request)


def _plaintext_response_with_headers(
    content: str,
    *,
    headers: dict[str, str] | None = None,
    status_code: int = 200,
) -> PlainTextResponse:
    response = PlainTextResponse(content, status_code=status_code)
    for name, value in (headers or {}).items():
        header_name = str(name).strip()
        header_value = str(value)
        try:
            response.headers[header_name] = header_value
        except UnicodeEncodeError:
            response.raw_headers.append((header_name.lower().encode("ascii"), header_value.encode("utf-8")))
    return response


def _query_flag(query_params, name: str) -> bool:
    value = str(query_params.get(name) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _bridge_cookie_secret() -> str:
    return str(config.platega_webhook_secret or config.bot_token or "amonora-bridge")


def _sign_bridge_cookie(timestamp: int) -> str:
    raw = str(timestamp).encode("utf-8")
    signature = hmac.new(_bridge_cookie_secret().encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return f"{timestamp}:{signature}"


def _read_bridge_cookie(value: str | None) -> datetime | None:
    if not value or ":" not in value:
        return None
    raw_ts, signature = value.split(":", 1)
    if not raw_ts.isdigit():
        return None
    expected = hmac.new(_bridge_cookie_secret().encode("utf-8"), raw_ts.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    return datetime.utcfromtimestamp(int(raw_ts))


def _bridge_cookie_retry_at(request: Request) -> datetime | None:
    issued_at = _read_bridge_cookie(request.cookies.get(BRIDGE_ACCESS_COOKIE_NAME))
    if issued_at is None:
        return None
    retry_at = issued_at + timedelta(seconds=BRIDGE_ACCESS_RATE_LIMIT_SECONDS)
    if retry_at <= datetime.utcnow():
        return None
    return retry_at


async def _consume_bridge_rate_limit(client_ip: str) -> datetime | None:
    if not client_ip:
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

        last_issued_at = _bridge_issue_timestamps.get(client_ip)
        if last_issued_at and last_issued_at > now - timedelta(seconds=BRIDGE_ACCESS_RATE_LIMIT_SECONDS):
            return last_issued_at + timedelta(seconds=BRIDGE_ACCESS_RATE_LIMIT_SECONDS)

        _bridge_issue_timestamps[client_ip] = now
        return None


async def _release_bridge_rate_limit(client_ip: str) -> None:
    if not client_ip:
        return
    async with _bridge_issue_lock:
        _bridge_issue_timestamps.pop(client_ip, None)


async def _issue_bridge_vless_key(user_id: int, access_expires_at: datetime) -> dict:
    # Parallel health check across all regions
    async def check_region(cc: str) -> tuple[str, bool]:
        provisioner = get_vless_provisioner(cc)
        try:
            return (cc, await provisioner.health_check())
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


def render_markdown_page(
    request: Request,
    *,
    slug: str,
    page_title: str,
    page_description: str,
    page_eyebrow: str,
    page_links: list[dict[str, str]] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    markdown_path = _resolve_docs_page(slug)
    if markdown_path is None:
        return _render_not_found_page(
            request,
            page_title="Документ недоступен",
            page_description="Запрошенный документ сейчас недоступен.",
            page_eyebrow=page_eyebrow,
            document_description="Запрошенный документ сейчас недоступен или был перемещён. Вернитесь на главную страницу и продолжите навигацию оттуда.",
        )

    markdown_text = markdown_path.read_text(encoding="utf-8")
    document_html = markdown.markdown(
        markdown_text,
        extensions=["extra", "fenced_code", "tables", "sane_lists"],
    )
    return _render_markdown_template(
        request,
        page_title=page_title,
        page_description=page_description,
        page_eyebrow=page_eyebrow,
        page_links=page_links,
        document_html=document_html,
        status_code=status_code,
    )


def _should_redirect_landing(request: Request) -> bool:
    return _is_client_public_host(request) and request.method in {"GET", "HEAD"}


@app.get("/", response_class=HTMLResponse)
async def landing_index(request: Request):
    if _should_redirect_landing(request):
        return RedirectResponse(PUBLIC_WEB_BASE_URL, status_code=302)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            **build_context(),
            "canonical_url": _canonical_public_url(request),
        },
    )


@app.head("/")
async def landing_head(request: Request):
    if _should_redirect_landing(request):
        return RedirectResponse(PUBLIC_WEB_BASE_URL, status_code=302)
    return Response(status_code=200, media_type="text/html")


@app.get("/{filename}.txt", response_class=PlainTextResponse)
async def verification_file(filename: str):
    content = VERIFICATION_FILES.get(filename)
    if content is None:
        return PlainTextResponse("Not Found", status_code=404)
    return PlainTextResponse(content)


@app.get("/legal/{page_key}", response_class=HTMLResponse)
async def legal_page(request: Request, page_key: str):
    page = LEGAL_PAGES.get(page_key)
    if page is None:
        return _render_not_found_page(
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


@app.get("/manual", response_class=HTMLResponse)
async def manual_page(request: Request):
    if _is_client_public_host(request):
        return RedirectResponse(f"{PUBLIC_WEB_BASE_URL}/manual", status_code=302)
    return render_markdown_page(
        request,
        slug=MANUAL_PAGE["slug"],
        page_title=MANUAL_PAGE["title"],
        page_description=MANUAL_PAGE["description"],
        page_eyebrow=MANUAL_PAGE["eyebrow"],
    )


@app.get("/health", response_class=JSONResponse)
async def healthcheck():
    checks: dict[str, str | float] = {"service": "amonora-landing"}

    # Database
    try:
        async with async_session() as session:
            import sqlalchemy as sa
            result = await session.execute(sa.text("SELECT 1"))
            result.scalar()
        checks["db"] = "ok"
    except Exception as exc:
        checks["db"] = str(exc)[:64]

    # VPN provisioners (DK, DE)
    vpn_checks: list[dict] = []
    provisioner_tasks = [
        _check_provisioner_health("dk"),
        _check_provisioner_health("de"),
    ]
    results = await asyncio.gather(*provisioner_tasks, return_exceptions=True)
    for cc, ok in results:
        if isinstance(ok, Exception):
            vpn_checks.append({"region": cc, "status": f"error: {type(ok).__name__}"})
        else:
            vpn_checks.append({"region": cc, "status": "ok" if ok else "unhealthy"})
    checks["vpn_regions"] = vpn_checks

    all_ok = checks.get("db") == "ok"
    checks["ok"] = all_ok
    return JSONResponse(checks, status_code=200 if all_ok else 503)


async def _check_provisioner_health(country_code: str) -> tuple[str, bool | Exception]:
    try:
        provisioner = get_vless_provisioner(country_code)
        try:
            return (country_code, await provisioner.health_check())
        finally:
            await provisioner.close()
    except Exception as exc:
        return (country_code, exc)


async def _public_subscription_feed_response(
    request: Request,
    token: str,
    *,
    force_client_binding: bool,
):
    slot_index: int | None = None
    include_extra = _query_flag(request.query_params, "include_extra")
    if force_client_binding or is_public_subscription_client_request(request.headers, query_params=request.query_params):
        request_context = build_public_subscription_request_context(
            headers=request.headers,
            source_ip=_client_ip(request),
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
    return _plaintext_response_with_headers(content, headers=headers)


@app.get("/api/public/subscriptions/{token}/summary", response_class=JSONResponse)
async def public_subscription_summary(request: Request, token: str):
    if not _is_client_public_host(request):
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    summary = await get_public_subscription_summary_by_token(token)
    if summary is None:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    return {"ok": True, "subscription": summary}


@app.post("/api/public/subscriptions/{token}/touch", response_class=JSONResponse)
async def public_subscription_touch(request: Request, token: str):
    if not _is_client_public_host(request):
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    if not is_valid_public_subscription_token(token):
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    touched = await touch_public_subscription_surface(token, feed_access=False)
    if not touched:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    return {"ok": True}


@app.get("/sub/{token}", response_class=PlainTextResponse)
async def public_subscription_feed(request: Request, token: str):
    if not _is_client_public_host(request):
        return PlainTextResponse("Not Found", status_code=404)
    return await _public_subscription_feed_response(request, token, force_client_binding=False)


@app.get("/happ/add", response_class=HTMLResponse)
async def public_subscription_happ_wrapper(request: Request):
    if not _is_client_public_host(request):
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


@app.post("/bridge/access", response_class=JSONResponse)
async def bridge_access(request: Request):
    client_ip = _client_ip(request)
    cookie_retry_at = _bridge_cookie_retry_at(request)
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
    retry_at = await _consume_bridge_rate_limit(client_ip)
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
        payload = await _issue_bridge_vless_key(user.id, access_expires_at)
    except Exception:
        await _release_bridge_rate_limit(client_ip)
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
        _sign_bridge_cookie(int(datetime.utcnow().timestamp())),
        max_age=BRIDGE_ACCESS_RATE_LIMIT_SECONDS,
        httponly=True,
        secure=True,
        samesite="Lax",
    )
    return response


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


@app.get("/{token}")
async def public_subscription_page(request: Request, token: str):
    if not _is_client_public_host(request):
        if _should_render_html_not_found(request):
            return _render_not_found_page(request)
        return PlainTextResponse("Not Found", status_code=404)
    if not is_valid_public_subscription_token(token):
        return PlainTextResponse("Not Found", status_code=404)
    if is_public_subscription_client_request(request.headers, query_params=request.query_params):
        feed_url = build_public_subscription_feed_url(token)
        if _query_flag(request.query_params, "include_extra"):
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
