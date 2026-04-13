import unittest

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import dashboard.main as dashboard_main
import dashboard.services as dashboard_services
from dashboard.services import create_session, dashboard_settings
from tests.test_dashboard_auth_session import FakeAsyncSession, MemoryStore


class DashboardSupportAttachmentRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.store = MemoryStore()
        cls.startup_handlers = list(dashboard_main.app.router.on_startup)
        dashboard_main.app.router.on_startup.clear()
        cls.client_cm = TestClient(dashboard_main.app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_cm.__exit__(None, None, None)
        dashboard_main.app.router.on_startup[:] = cls.startup_handlers

    def setUp(self) -> None:
        self.store.reset()
        self.client.cookies.clear()

    def fake_session_factory(self):
        return FakeAsyncSession(self.store)

    def set_session_cookie(self, token: str) -> None:
        self.client.cookies.set(dashboard_settings()["cookie_name"], token)

    def test_attachment_route_requires_session(self) -> None:
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            response = self.client.get("/dashboard/support/5001/messages/12/attachment", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login")

    def test_attachment_route_streams_attachment_for_authorized_admin(self) -> None:
        token = "support-attachment-token"
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(
                dashboard_main,
                "get_support_attachment_content",
                return_value={
                    "filename": "support-photo.jpg",
                    "media_type": "image/jpeg",
                    "content": b"fake-image",
                },
            ),
        ):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.get("/dashboard/support/5001/messages/12/attachment")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"fake-image")
        self.assertEqual(response.headers["content-type"], "image/jpeg")
        self.assertIn("support-photo.jpg", response.headers["content-disposition"])

    def test_support_ticket_detail_exposes_attachment_url_in_history(self) -> None:
        with (
            patch.object(
                dashboard_services,
                "get_ticket",
                new=AsyncMock(return_value={"user_id": 5001, "status": "new"}),
            ),
            patch.object(
                dashboard_services,
                "get_history",
                new=AsyncMock(
                    return_value=[
                        {
                            "id": 12,
                            "sender": "user",
                            "text": "photo",
                            "attachment": {
                                "kind": "photo",
                                "name": "support-photo.jpg",
                                "mime_type": "image/jpeg",
                                "size": 12345,
                            },
                        }
                    ]
                ),
            ),
            patch.object(dashboard_services, "get_user_by_id", new=AsyncMock(return_value=None)),
            patch.object(dashboard_services, "get_user_by_telegram_id", new=AsyncMock(return_value=None)),
        ):
            detail = self._run(dashboard_services.get_support_ticket_detail(5001))

        self.assertIsNotNone(detail)
        self.assertEqual(
            detail["history"][0]["attachment"]["url"],
            "/dashboard/support/5001/messages/12/attachment",
        )


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)


DashboardSupportAttachmentRouteTests._run = staticmethod(_run_async)


if __name__ == "__main__":
    unittest.main()
