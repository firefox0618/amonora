from contextlib import asynccontextmanager
from datetime import datetime
import functools
import logging
from pathlib import Path
from uuid import uuid4

import markdown
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.core.tracing import reset_current_trace_id, set_current_trace_id
from bot.config import config
from bot.public_subscription import is_public_subscription_client_host
from bot.utils.logging_setup import configure_logging
from bot.utils.tariffs import get_tariffs_list


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent.parent
DOCS_DIR = ROOT_DIR / "docs"
SITE_APP_DIR = ROOT_DIR / "apps" / "site"
CLIENT_APP_DIR = ROOT_DIR / "apps" / "client"
SITE_STATIC_DIR = SITE_APP_DIR / "static"
CLIENT_STATIC_DIR = CLIENT_APP_DIR / "static" / "client-app"
SITE_TEMPLATES_DIR = SITE_APP_DIR / "templates"
CLIENT_TEMPLATES_DIR = CLIENT_APP_DIR / "templates"
templates = Jinja2Templates(directory=[str(SITE_TEMPLATES_DIR), str(CLIENT_TEMPLATES_DIR)])

PUBLIC_WEB_BASE_URL = config.public_site_base_url.rstrip("/")
PUBLIC_WEB_CANONICAL_HOST = config.public_site_host
PUBLIC_WEB_ALLOWED_HOSTS = frozenset(config.public_site_hosts)
CLIENT_APP_ASSET_VERSION = "20260515-client-domain-v6"
BRIDGE_ACCESS_DURATION_DAYS = 1
BRIDGE_ACCESS_REGION_ORDER = ("dk", "de")
BRIDGE_ACCESS_RATE_LIMIT_SECONDS = 30 * 60
BRIDGE_ACCESS_DEVICE_NAME = "Amonora Bridge"
BRIDGE_ACCESS_COOKIE_NAME = "amonora_bridge_cooldown"

SAFE_ERROR_MESSAGE = "Внутренняя ошибка сервера. Попробуйте обновить страницу."
SAFE_ERROR_HTML = (
    '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
    '<title>Ошибка</title></head><body style="font-family:sans-serif;padding:2rem;text-align:center">'
    f"<h1>Ошибка</h1><p>{SAFE_ERROR_MESSAGE}</p></body></html>"
)
_LANDING_LOGGER = logging.getLogger("landing")


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    yield


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
        "og_image_url": public_static_url("og-image.png"),
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


def request_host(request: Request) -> str:
    return request.headers.get("host", "").split(":", 1)[0].strip().lower()


def is_client_public_host_request(request: Request) -> bool:
    return is_public_subscription_client_host(request_host(request))


def canonical_public_url(request: Request) -> str:
    path = request.url.path or "/"
    query = f"?{request.url.query}" if request.url.query else ""
    return f"{PUBLIC_WEB_BASE_URL}{path}{query}"


def public_static_url(path: str) -> str:
    return f"{PUBLIC_WEB_BASE_URL}/static/{path.lstrip('/')}"


def should_redirect_public_request(request: Request) -> bool:
    if request.method not in {"GET", "HEAD"}:
        return False
    req_host = request_host(request)
    if req_host not in PUBLIC_WEB_ALLOWED_HOSTS or req_host == PUBLIC_WEB_CANONICAL_HOST:
        return False
    path = request.url.path or "/"
    return path == "/" or path == "/manual" or path.startswith("/legal/")


async def canonical_public_host_middleware(request: Request, call_next):
    if should_redirect_public_request(request):
        return RedirectResponse(canonical_public_url(request), status_code=308)
    return await call_next(request)


async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    _LANDING_LOGGER.exception(
        "Unhandled exception",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "client_ip": client_ip(request),
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


async def landing_request_id_middleware(request: Request, call_next):
    raw_request_id = str(request.headers.get("x-request-id") or "").strip()
    request_id = raw_request_id[:64] if raw_request_id else uuid4().hex
    request.state.request_id = request_id
    token = set_current_trace_id(request_id)
    try:
        response = await call_next(request)
    finally:
        reset_current_trace_id(token)
    response.headers.setdefault("X-Request-ID", request_id)
    return response


async def static_cache_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path.startswith("/client-static/"):
        response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
    return response


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded.strip():
        return forwarded.split(",", 1)[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def render_markdown_template(
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
            "canonical_url": canonical_public_url(request),
            "page_title": page_title,
            "page_description": page_description,
            "page_eyebrow": page_eyebrow,
            "page_links": page_links or [],
            "document_html": document_html,
        },
        status_code=status_code,
    )


def resolve_docs_page(slug: str) -> Path | None:
    candidate = (DOCS_DIR / slug).resolve()
    try:
        candidate.relative_to(DOCS_DIR.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def not_found_document_html(
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


def render_not_found_page(
    request: Request,
    *,
    page_title: str = "Страница не найдена",
    page_description: str = "Страница не найдена или недоступна.",
    page_eyebrow: str = "ошибка навигации",
    document_title: str = "Страница не найдена или недоступна",
    document_description: str = "Проверь адрес страницы или вернись на главную, чтобы продолжить навигацию по Amonora.",
) -> HTMLResponse:
    return render_markdown_template(
        request,
        page_title=page_title,
        page_description=page_description,
        page_eyebrow=page_eyebrow,
        document_html=not_found_document_html(
            title=document_title,
            description=document_description,
        ),
        status_code=404,
    )


def should_render_html_not_found(request: Request) -> bool:
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


async def global_not_found_handler(request: Request, _: StarletteHTTPException):
    if not should_render_html_not_found(request):
        return PlainTextResponse("Not Found", status_code=404)
    return render_not_found_page(request)


def plaintext_response_with_headers(
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


def query_flag(query_params, name: str) -> bool:
    value = str(query_params.get(name) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


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
    markdown_path = resolve_docs_page(slug)
    if markdown_path is None:
        return render_not_found_page(
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
    return render_markdown_template(
        request,
        page_title=page_title,
        page_description=page_description,
        page_eyebrow=page_eyebrow,
        page_links=page_links,
        document_html=document_html,
        status_code=status_code,
    )


def setup_common_public_app(app: FastAPI, *, redirect_public_hosts: bool) -> None:
    if redirect_public_hosts:
        app.middleware("http")(canonical_public_host_middleware)
    app.middleware("http")(landing_request_id_middleware)
    app.middleware("http")(static_cache_headers_middleware)
    app.add_exception_handler(Exception, global_exception_handler)
    app.add_exception_handler(404, global_not_found_handler)
