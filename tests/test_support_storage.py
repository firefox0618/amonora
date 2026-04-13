import asyncio
from datetime import timedelta

from sqlalchemy import delete, select

from backend.core.database import async_session
from backend.core.models import SupportTicket, SupportTicketMessage
from bot.config import config
from bot.utils.access import utcnow
from support_bot import storage


TEST_USER_ID = 9900099001


class DummyPanelMessage:
    def __init__(self, message_id: int) -> None:
        self.message_id = message_id


class DummyBot:
    def __init__(self) -> None:
        self.sent_to: list[int] = []
        self.next_message_id = 100

    async def send_message(self, chat_id: int, text: str, parse_mode: str = "", reply_markup=None):
        del text, parse_mode, reply_markup
        self.sent_to.append(chat_id)
        self.next_message_id += 1
        return DummyPanelMessage(self.next_message_id)

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        parse_mode: str = "",
        reply_markup=None,
    ):
        del chat_id, message_id, text, parse_mode, reply_markup
        return None


async def _cleanup_test_ticket() -> None:
    async with async_session() as session:
        result = await session.execute(
            select(SupportTicket.id).where(SupportTicket.user_id == TEST_USER_ID)
        )
        ticket_id = result.scalar_one_or_none()
        if ticket_id is not None:
            await session.execute(
                delete(SupportTicketMessage).where(SupportTicketMessage.ticket_id == ticket_id)
            )
            await session.execute(delete(SupportTicket).where(SupportTicket.id == ticket_id))
            await session.commit()


async def main() -> None:
    original_admins = list(config.support_admin_ids)
    storage._STORAGE_READY = False
    config.support_admin_ids = [101, 202]

    try:
        await storage.bootstrap_storage()
        await _cleanup_test_ticket()

        ticket, reopened = await storage.register_user_message(
            user_id=TEST_USER_ID,
            username="support_db_test",
            full_name="Support DB Test",
            preview="Первый вопрос",
            content_type="text",
        )
        assert reopened is False
        assert ticket["status"] == "new"

        attachment_ticket, _ = await storage.register_user_message(
            user_id=TEST_USER_ID,
            username="support_db_test",
            full_name="Support DB Test",
            preview="📷 Фото",
            content_type="photo",
            attachment={
                "file_id": "photo-file-id",
                "file_unique_id": "photo-unique-id",
                "kind": "photo",
                "name": "support-photo.jpg",
                "mime_type": "image/jpeg",
                "size": 2048,
            },
        )
        assert attachment_ticket["messages"][-1]["attachment"]["kind"] == "photo"
        assert attachment_ticket["messages"][-1]["attachment"]["name"] == "support-photo.jpg"

        attachment_lookup = await storage.get_message_attachment(
            TEST_USER_ID,
            attachment_ticket["messages"][-1]["id"],
        )
        assert attachment_lookup is not None
        assert attachment_lookup["file_id"] == "photo-file-id"

        for idx in range(storage.MAX_MESSAGES_PER_TICKET + 7):
            await storage.register_user_message(
                user_id=TEST_USER_ID,
                username="support_db_test",
                full_name="Support DB Test",
                preview=f"Сообщение {idx}",
                content_type="text",
            )

        trimmed_ticket = await storage.get_ticket(TEST_USER_ID)
        assert trimmed_ticket is not None

        history = await storage.get_history(TEST_USER_ID)
        assert len(history) == storage.MAX_MESSAGES_PER_TICKET + 9

        updated_ticket = await storage.assign_ticket(TEST_USER_ID, 101, "Admin One")
        assert updated_ticket is not None
        assert updated_ticket["assigned_admin_id"] == 101

        updated_ticket = await storage.register_admin_reply(
            TEST_USER_ID,
            101,
            "Admin One",
            "Ответ поддержки",
            "text",
        )
        assert updated_ticket is not None
        assert updated_ticket["status"] == "in_progress"

        await storage.register_admin_card(TEST_USER_ID, 101, 77)
        ticket = await storage.get_ticket(TEST_USER_ID)
        assert ticket is not None
        assert ticket["admin_cards"]["101"] == [77]

        from support_bot import router as support_router

        dummy_bot = DummyBot()
        await support_router._push_ticket_to_admins(dummy_bot, ticket)
        assert dummy_bot.sent_to == [202]

        closed_ticket = await storage.close_ticket(TEST_USER_ID)
        assert closed_ticket is not None
        assert closed_ticket["status"] == "closed"

        reopened_ticket, reopened = await storage.register_user_message(
            user_id=TEST_USER_ID,
            username="support_db_test",
            full_name="Support DB Test",
            preview="Открываю заново",
            content_type="text",
        )
        assert reopened is True
        assert reopened_ticket["status"] == "new"

        async with async_session() as session:
            result = await session.execute(
                select(SupportTicket).where(SupportTicket.user_id == TEST_USER_ID)
            )
            ticket_record = result.scalar_one()
            ticket_record.status = "closed"
            ticket_record.closed_at = utcnow() - timedelta(days=storage.RETAIN_CLOSED_TICKETS_DAYS + 5)
            ticket_record.updated_at = ticket_record.closed_at
            await session.commit()

        tickets_after_prune = await storage.list_tickets("all")
        assert any(ticket["user_id"] == TEST_USER_ID for ticket in tickets_after_prune)

        counts = await storage.get_ticket_counts(admin_id=101)
        assert counts["all"] >= 0

        print("Support storage DB tests passed")
    finally:
        await _cleanup_test_ticket()
        config.support_admin_ids = original_admins
        storage._STORAGE_READY = False


if __name__ == "__main__":
    asyncio.run(main())
