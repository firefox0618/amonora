import asyncio
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import String, and_, cast, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import async_session, engine
from backend.core.models import SupportTicket, SupportTicketMessage, User
from backend.core.schema import ensure_schema
from backend.core.synthetic_users import real_user_sql_clause as shared_real_user_sql_clause, synthetic_username_sql_predicates


STORAGE_DIR = Path(__file__).resolve().parent / "data"
STORAGE_FILE = STORAGE_DIR / "support_tickets.json"
MAX_MESSAGES_PER_TICKET = 50
RETAIN_CLOSED_TICKETS_DAYS = 90

_LOCK = asyncio.Lock()
_INIT_LOCK = asyncio.Lock()
_TICKET_LOCKS: dict[str, asyncio.Lock] = {}
_STORAGE_READY = False
logger = logging.getLogger(__name__)


def _utcnow_dt() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def _utcnow() -> str:
    return _serialize_datetime(_utcnow_dt())


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    return value.isoformat(timespec="seconds")


def _deserialize_datetime(raw: str | datetime | None) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        value = raw
    else:
        try:
            value = datetime.fromisoformat(raw)
        except ValueError:
            return None
    if value.tzinfo is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value.replace(microsecond=0)


def _normalize_user_id(user_id: int) -> str:
    return str(user_id)


def _ticket_lock(user_id: int) -> asyncio.Lock:
    return _TICKET_LOCKS.setdefault(_normalize_user_id(user_id), asyncio.Lock())


def _real_support_ticket_clause():
    legacy_username_clause = ~or_(*synthetic_username_sql_predicates(SupportTicket.username))
    return or_(
        and_(User.id.is_not(None), shared_real_user_sql_clause(User)),
        and_(User.id.is_(None), legacy_username_clause),
    )


def _default_data() -> dict[str, Any]:
    return {"tickets": {}}


def _base_ticket(user_id: int, username: str | None, full_name: str) -> dict[str, Any]:
    now = _utcnow()
    return {
        "user_id": user_id,
        "username": username,
        "full_name": full_name,
        "status": "new",
        "assigned_admin_id": None,
        "assigned_admin_name": None,
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "last_message_preview": "",
        "last_user_message_preview": "",
        "last_admin_reply_preview": "",
        "messages": [],
        "admin_cards": {},
    }


def _effective_status(ticket: dict[str, Any]) -> str:
    status = ticket.get("status")
    if status in {"new", "in_progress", "closed"}:
        return status
    if status == "open":
        return "in_progress" if ticket.get("assigned_admin_id") else "new"
    return "new"


def _normalize_ticket(ticket: dict[str, Any]) -> dict[str, Any]:
    ticket.setdefault("username", None)
    ticket.setdefault("full_name", "Неизвестно")
    ticket.setdefault("assigned_admin_id", None)
    ticket.setdefault("assigned_admin_name", None)
    ticket.setdefault("created_at", _utcnow())
    ticket.setdefault("updated_at", ticket["created_at"])
    ticket.setdefault("closed_at", None)
    ticket.setdefault("last_message_preview", "")
    ticket.setdefault("last_user_message_preview", "")
    ticket.setdefault("last_admin_reply_preview", "")
    ticket.setdefault("messages", [])
    ticket.setdefault("admin_cards", {})
    ticket["status"] = _effective_status(ticket)
    return ticket


def _read_legacy_data() -> dict[str, Any]:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    if not STORAGE_FILE.exists():
        return _default_data()

    try:
        return json.loads(STORAGE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        backup_file = STORAGE_FILE.with_suffix(
            f".corrupt-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.json"
        )
        try:
            os.replace(STORAGE_FILE, backup_file)
            logger.warning("Support storage was corrupted and moved to %s", backup_file)
        except OSError:
            logger.exception("Support storage was corrupted and could not be moved aside")
        return _default_data()


def _parse_admin_cards(raw: str | None) -> dict[str, list[int]]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}

    normalized: dict[str, list[int]] = {}
    for admin_key, message_ids in data.items():
        if not isinstance(message_ids, list):
            continue
        valid_ids = []
        for message_id in message_ids:
            try:
                valid_ids.append(int(message_id))
            except (TypeError, ValueError):
                continue
        if valid_ids:
            normalized[str(admin_key)] = valid_ids[-20:]
    return normalized


def _serialize_admin_cards(admin_cards: dict[str, list[int]]) -> str:
    normalized = {
        str(admin_id): [int(message_id) for message_id in message_ids[-20:]]
        for admin_id, message_ids in admin_cards.items()
        if message_ids
    }
    return json.dumps(normalized, ensure_ascii=False)


def _normalize_attachment(attachment: dict[str, Any] | None) -> dict[str, Any] | None:
    if not attachment:
        return None

    file_id = str(attachment.get("file_id") or "").strip()
    if not file_id:
        return None

    file_unique_id = str(attachment.get("file_unique_id") or "").strip() or None
    kind = str(attachment.get("kind") or "").strip() or None
    name = str(attachment.get("name") or "").strip() or None
    mime_type = str(attachment.get("mime_type") or "").strip() or None
    try:
        size = int(attachment.get("size")) if attachment.get("size") is not None else None
    except (TypeError, ValueError):
        size = None

    return {
        "file_id": file_id,
        "file_unique_id": file_unique_id,
        "kind": kind,
        "name": name,
        "mime_type": mime_type,
        "size": size,
    }


def _attachment_to_dict(message: SupportTicketMessage) -> dict[str, Any] | None:
    if not message.attachment_file_id:
        return None
    return {
        "kind": message.attachment_kind,
        "name": message.attachment_name,
        "mime_type": message.attachment_mime_type,
        "size": message.attachment_size,
    }


def _message_to_dict(message: SupportTicketMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "role": message.role,
        "sender_id": message.sender_id,
        "sender_name": message.sender_name,
        "content_type": message.content_type,
        "text": message.text,
        "timestamp": _serialize_datetime(message.created_at),
        "attachment": _attachment_to_dict(message),
    }


def _ticket_to_dict(
    ticket: SupportTicket,
    messages: list[SupportTicketMessage] | None = None,
) -> dict[str, Any]:
    payload = {
        "user_id": ticket.user_id,
        "username": ticket.username,
        "full_name": ticket.full_name,
        "status": _effective_status({"status": ticket.status, "assigned_admin_id": ticket.assigned_admin_id}),
        "assigned_admin_id": ticket.assigned_admin_id,
        "assigned_admin_name": ticket.assigned_admin_name,
        "created_at": _serialize_datetime(ticket.created_at),
        "updated_at": _serialize_datetime(ticket.updated_at),
        "closed_at": _serialize_datetime(ticket.closed_at),
        "last_message_preview": ticket.last_message_preview or "",
        "last_user_message_preview": ticket.last_user_message_preview or "",
        "last_admin_reply_preview": ticket.last_admin_reply_preview or "",
        "admin_cards": _parse_admin_cards(ticket.admin_cards_json),
    }
    if messages is not None:
        payload["messages"] = [_message_to_dict(message) for message in messages]
    return payload


async def _get_ticket_record(session: AsyncSession, user_id: int) -> SupportTicket | None:
    result = await session.execute(
        select(SupportTicket).where(SupportTicket.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _get_ticket_messages(
    session: AsyncSession,
    ticket_id: int,
) -> list[SupportTicketMessage]:
    result = await session.execute(
        select(SupportTicketMessage)
        .where(SupportTicketMessage.ticket_id == ticket_id)
        .order_by(SupportTicketMessage.created_at.asc(), SupportTicketMessage.id.asc())
    )
    return list(result.scalars().all())


async def _trim_messages(session: AsyncSession, ticket_id: int) -> None:
    del session, ticket_id
    # History should remain intact; rendering and pagination must handle volume instead.
    return


async def _prune_closed_tickets(session: AsyncSession) -> None:
    del session
    # Closed tickets are retained for audit/support history.
    return


async def _migrate_legacy_file(session: AsyncSession) -> None:
    if not STORAGE_FILE.exists():
        return

    count_result = await session.execute(select(SupportTicket.id).limit(1))
    if count_result.scalar_one_or_none() is not None:
        return

    legacy_data = _read_legacy_data()
    tickets = legacy_data.get("tickets", {})
    if not isinstance(tickets, dict) or not tickets:
        return

    for raw_ticket in tickets.values():
        ticket_data = _normalize_ticket(raw_ticket if isinstance(raw_ticket, dict) else {})
        ticket = SupportTicket(
            user_id=int(ticket_data.get("user_id") or 0),
            username=ticket_data.get("username"),
            full_name=ticket_data.get("full_name") or "Неизвестно",
            status=ticket_data.get("status") or "new",
            assigned_admin_id=ticket_data.get("assigned_admin_id"),
            assigned_admin_name=ticket_data.get("assigned_admin_name"),
            last_message_preview=ticket_data.get("last_message_preview") or "",
            last_user_message_preview=ticket_data.get("last_user_message_preview") or "",
            last_admin_reply_preview=ticket_data.get("last_admin_reply_preview") or "",
            admin_cards_json=_serialize_admin_cards(ticket_data.get("admin_cards", {})),
            created_at=_deserialize_datetime(ticket_data.get("created_at")) or _utcnow_dt(),
            updated_at=_deserialize_datetime(ticket_data.get("updated_at")) or _utcnow_dt(),
            closed_at=_deserialize_datetime(ticket_data.get("closed_at")),
        )
        session.add(ticket)
        await session.flush()

        messages = ticket_data.get("messages", [])
        for message in messages:
            if not isinstance(message, dict):
                continue
            attachment = _normalize_attachment(message.get("attachment"))
            session.add(
                SupportTicketMessage(
                    ticket_id=ticket.id,
                    role=str(message.get("role") or "user"),
                    sender_id=int(message.get("sender_id") or ticket.user_id),
                    sender_name=str(message.get("sender_name") or ticket.full_name),
                    content_type=str(message.get("content_type") or "text"),
                    text=str(message.get("text") or ""),
                    attachment_file_id=attachment["file_id"] if attachment else None,
                    attachment_file_unique_id=attachment["file_unique_id"] if attachment else None,
                    attachment_kind=attachment["kind"] if attachment else None,
                    attachment_name=attachment["name"] if attachment else None,
                    attachment_mime_type=attachment["mime_type"] if attachment else None,
                    attachment_size=attachment["size"] if attachment else None,
                    created_at=_deserialize_datetime(message.get("timestamp")) or ticket.updated_at,
                )
            )

    await session.commit()

    migrated_path = STORAGE_FILE.with_suffix(
        f".migrated-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.json"
    )
    try:
        os.replace(STORAGE_FILE, migrated_path)
        logger.info("Migrated legacy support tickets to database and archived %s", migrated_path)
    except OSError:
        logger.exception("Support tickets were migrated but legacy file could not be archived")


async def _ensure_support_tables() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(SupportTicket.__table__.create, checkfirst=True)
        await connection.run_sync(SupportTicketMessage.__table__.create, checkfirst=True)


async def bootstrap_storage() -> None:
    global _STORAGE_READY

    if _STORAGE_READY:
        return

    async with _INIT_LOCK:
        if _STORAGE_READY:
            return
        await ensure_schema()
        await _ensure_support_tables()
        async with async_session() as session:
            await _migrate_legacy_file(session)
        _STORAGE_READY = True


async def get_ticket(user_id: int) -> dict[str, Any] | None:
    await bootstrap_storage()
    async with async_session() as session:
        ticket = await _get_ticket_record(session, user_id)
        if ticket is None:
            return None
        return _ticket_to_dict(ticket)


async def register_user_message(
    user_id: int,
    username: str | None,
    full_name: str,
    preview: str,
    content_type: str,
    attachment: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    await bootstrap_storage()
    async with _ticket_lock(user_id):
        async with async_session() as session:
            await _prune_closed_tickets(session)
            ticket = await _get_ticket_record(session, user_id)
            reopened = False
            now = _utcnow_dt()

            if ticket is None:
                ticket = SupportTicket(
                    user_id=user_id,
                    username=username,
                    full_name=full_name,
                    status="new",
                    created_at=now,
                    updated_at=now,
                    last_message_preview=preview,
                    last_user_message_preview=preview,
                    last_admin_reply_preview="",
                    admin_cards_json="{}",
                )
                session.add(ticket)
                await session.flush()
            else:
                if ticket.status == "closed":
                    reopened = True
                    ticket.status = "new"
                    ticket.assigned_admin_id = None
                    ticket.assigned_admin_name = None
                    ticket.closed_at = None

                ticket.username = username
                ticket.full_name = full_name
                ticket.updated_at = now
                ticket.last_message_preview = preview
                ticket.last_user_message_preview = preview

            normalized_attachment = _normalize_attachment(attachment)
            session.add(
                SupportTicketMessage(
                    ticket_id=ticket.id,
                    role="user",
                    sender_id=user_id,
                    sender_name=full_name,
                    content_type=content_type,
                    text=preview,
                    attachment_file_id=normalized_attachment["file_id"] if normalized_attachment else None,
                    attachment_file_unique_id=normalized_attachment["file_unique_id"] if normalized_attachment else None,
                    attachment_kind=normalized_attachment["kind"] if normalized_attachment else None,
                    attachment_name=normalized_attachment["name"] if normalized_attachment else None,
                    attachment_mime_type=normalized_attachment["mime_type"] if normalized_attachment else None,
                    attachment_size=normalized_attachment["size"] if normalized_attachment else None,
                    created_at=now,
                )
            )
            await _trim_messages(session, ticket.id)
            await session.commit()
            messages = await _get_ticket_messages(session, ticket.id)
            return _ticket_to_dict(ticket, messages), reopened


async def register_admin_reply(
    user_id: int,
    admin_id: int,
    admin_name: str,
    preview: str,
    content_type: str,
    attachment: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    await bootstrap_storage()
    async with _ticket_lock(user_id):
        async with async_session() as session:
            await _prune_closed_tickets(session)
            ticket = await _get_ticket_record(session, user_id)
            if ticket is None:
                return None

            now = _utcnow_dt()
            ticket.status = "in_progress"
            ticket.closed_at = None
            ticket.updated_at = now
            ticket.last_message_preview = preview
            ticket.last_admin_reply_preview = preview
            ticket.assigned_admin_id = admin_id
            ticket.assigned_admin_name = admin_name

            normalized_attachment = _normalize_attachment(attachment)
            session.add(
                SupportTicketMessage(
                    ticket_id=ticket.id,
                    role="admin",
                    sender_id=admin_id,
                    sender_name=admin_name,
                    content_type=content_type,
                    text=preview,
                    attachment_file_id=normalized_attachment["file_id"] if normalized_attachment else None,
                    attachment_file_unique_id=normalized_attachment["file_unique_id"] if normalized_attachment else None,
                    attachment_kind=normalized_attachment["kind"] if normalized_attachment else None,
                    attachment_name=normalized_attachment["name"] if normalized_attachment else None,
                    attachment_mime_type=normalized_attachment["mime_type"] if normalized_attachment else None,
                    attachment_size=normalized_attachment["size"] if normalized_attachment else None,
                    created_at=now,
                )
            )
            await _trim_messages(session, ticket.id)
            await session.commit()
            messages = await _get_ticket_messages(session, ticket.id)
            return _ticket_to_dict(ticket, messages)


async def assign_ticket(user_id: int, admin_id: int, admin_name: str) -> dict[str, Any] | None:
    await bootstrap_storage()
    async with _ticket_lock(user_id):
        async with async_session() as session:
            await _prune_closed_tickets(session)
            ticket = await _get_ticket_record(session, user_id)
            if ticket is None:
                return None

            ticket.status = "in_progress"
            ticket.closed_at = None
            ticket.assigned_admin_id = admin_id
            ticket.assigned_admin_name = admin_name
            ticket.updated_at = _utcnow_dt()
            await session.commit()
            return _ticket_to_dict(ticket)


async def transfer_ticket(
    user_id: int,
    to_admin_id: int,
    to_admin_name: str,
) -> dict[str, Any] | None:
    await bootstrap_storage()
    async with _ticket_lock(user_id):
        async with async_session() as session:
            await _prune_closed_tickets(session)
            ticket = await _get_ticket_record(session, user_id)
            if ticket is None:
                return None

            ticket.status = "in_progress"
            ticket.closed_at = None
            ticket.assigned_admin_id = to_admin_id
            ticket.assigned_admin_name = to_admin_name
            ticket.updated_at = _utcnow_dt()
            await session.commit()
            return _ticket_to_dict(ticket)


async def close_ticket(user_id: int) -> dict[str, Any] | None:
    await bootstrap_storage()
    async with _ticket_lock(user_id):
        async with async_session() as session:
            await _prune_closed_tickets(session)
            ticket = await _get_ticket_record(session, user_id)
            if ticket is None:
                return None

            now = _utcnow_dt()
            ticket.status = "closed"
            ticket.closed_at = now
            ticket.updated_at = now
            await session.commit()
            return _ticket_to_dict(ticket)


async def register_admin_card(user_id: int, admin_id: int, message_id: int) -> dict[str, Any] | None:
    await bootstrap_storage()
    async with _ticket_lock(user_id):
        async with async_session() as session:
            await _prune_closed_tickets(session)
            ticket = await _get_ticket_record(session, user_id)
            if ticket is None:
                return None

            admin_cards = _parse_admin_cards(ticket.admin_cards_json)
            admin_key = _normalize_user_id(admin_id)
            message_ids = admin_cards.setdefault(admin_key, [])
            if message_id not in message_ids:
                message_ids.append(message_id)
            admin_cards[admin_key] = message_ids[-20:]
            ticket.admin_cards_json = _serialize_admin_cards(admin_cards)
            await session.commit()
            return _ticket_to_dict(ticket)


async def replace_admin_cards(user_id: int, admin_cards: dict[str, list[int]]) -> dict[str, Any] | None:
    await bootstrap_storage()
    async with _ticket_lock(user_id):
        async with async_session() as session:
            await _prune_closed_tickets(session)
            ticket = await _get_ticket_record(session, user_id)
            if ticket is None:
                return None

            ticket.admin_cards_json = _serialize_admin_cards(admin_cards)
            await session.commit()
            return _ticket_to_dict(ticket)


async def get_history(user_id: int) -> list[dict[str, Any]]:
    await bootstrap_storage()
    async with async_session() as session:
        ticket = await _get_ticket_record(session, user_id)
        if ticket is None:
            return []
        messages = await _get_ticket_messages(session, ticket.id)
        return [_message_to_dict(message) for message in messages]


async def get_message_attachment(user_id: int, message_id: int) -> dict[str, Any] | None:
    await bootstrap_storage()
    async with async_session() as session:
        ticket = await _get_ticket_record(session, user_id)
        if ticket is None:
            return None
        result = await session.execute(
            select(SupportTicketMessage).where(
                SupportTicketMessage.ticket_id == ticket.id,
                SupportTicketMessage.id == message_id,
            )
        )
        message = result.scalar_one_or_none()
        if message is None or not message.attachment_file_id:
            return None
        return {
            "message_id": message.id,
            "file_id": message.attachment_file_id,
            "file_unique_id": message.attachment_file_unique_id,
            "kind": message.attachment_kind,
            "name": message.attachment_name,
            "mime_type": message.attachment_mime_type,
            "size": message.attachment_size,
        }


async def list_tickets(
    filter_mode: str = "queue",
    admin_id: int | None = None,
    *,
    limit: int | None = None,
    search: str = "",
    exclude_synthetic: bool = False,
) -> list[dict[str, Any]]:
    await bootstrap_storage()
    async with async_session() as session:
        await _prune_closed_tickets(session)
        await session.commit()
        query = select(SupportTicket).order_by(SupportTicket.updated_at.desc(), SupportTicket.id.desc())
        if exclude_synthetic:
            query = query.outerjoin(User, User.telegram_id == SupportTicket.user_id).where(_real_support_ticket_clause())
        if filter_mode == "queue":
            query = query.where(SupportTicket.status.in_(("new", "in_progress")))
        elif filter_mode == "mine" and admin_id is not None:
            query = query.where(SupportTicket.assigned_admin_id == admin_id)
        elif filter_mode == "new":
            query = query.where(SupportTicket.status == "new")
        elif filter_mode == "closed":
            query = query.where(SupportTicket.status == "closed")
        elif filter_mode == "in_progress":
            query = query.where(SupportTicket.status == "in_progress")
        needle = search.strip().lower()
        if needle:
            like_pattern = f"%{needle}%"
            query = query.where(
                or_(
                    func.lower(cast(SupportTicket.user_id, String)).like(like_pattern),
                    func.lower(func.coalesce(SupportTicket.username, "")).like(like_pattern),
                    func.lower(func.coalesce(SupportTicket.full_name, "")).like(like_pattern),
                    func.lower(func.coalesce(SupportTicket.last_user_message_preview, "")).like(like_pattern),
                )
            )
        if limit is not None and int(limit) > 0:
            query = query.limit(int(limit))
        result = await session.execute(query)
        tickets = []
        for ticket in result.scalars().all():
            payload = _ticket_to_dict(ticket)
            tickets.append(payload)

        return tickets


async def get_ticket_counts(admin_id: int | None = None, *, exclude_synthetic: bool = False) -> dict[str, int]:
    await bootstrap_storage()
    async with async_session() as session:
        await _prune_closed_tickets(session)
        await session.commit()

        base_filters = []
        count_query = select(func.count()).select_from(SupportTicket)
        if exclude_synthetic:
            count_query = count_query.outerjoin(User, User.telegram_id == SupportTicket.user_id)
            base_filters.append(_real_support_ticket_clause())

        counts = {
            "all": int(
                (
                    await session.execute(
                        count_query
                        .where(*base_filters)
                    )
                ).scalar_one()
                or 0
            ),
            "new": int(
                (
                    await session.execute(
                        count_query
                        .where(*base_filters)
                        .where(SupportTicket.status == "new")
                    )
                ).scalar_one()
                or 0
            ),
            "in_progress": int(
                (
                    await session.execute(
                        count_query
                        .where(*base_filters)
                        .where(SupportTicket.status == "in_progress")
                    )
                ).scalar_one()
                or 0
            ),
            "closed": int(
                (
                    await session.execute(
                        count_query
                        .where(*base_filters)
                        .where(SupportTicket.status == "closed")
                    )
                ).scalar_one()
                or 0
            ),
            "mine": 0,
        }
        if admin_id is not None:
            counts["mine"] = int(
                (
                    await session.execute(
                        count_query
                        .where(*base_filters)
                        .where(SupportTicket.assigned_admin_id == admin_id)
                    )
                ).scalar_one()
                or 0
            )
    return counts
