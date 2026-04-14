import os
import unittest


os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "1")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASS", "test")
os.environ.setdefault("XUI_URL", "http://127.0.0.1:12053")
os.environ.setdefault("XUI_USERNAME", "test")
os.environ.setdefault("XUI_PASSWORD", "test")
os.environ.setdefault("CHANNEL_ID", "1")

from bot.handlers.cabinet import router as cabinet_router
from bot.handlers.devices import router as devices_router
from bot.handlers.info import router as info_router
from bot.handlers.protocol import router as protocol_router
from bot.handlers.referrals import router as referrals_router
from bot.handlers.start import router as start_router
from bot.handlers.support import router as support_router
from bot.handlers.tariffs import router as tariffs_router
from bot.main import dp
from bot.router import router as main_router


class BotMainRouterRegistrationTests(unittest.TestCase):
    def test_dispatcher_includes_main_and_runtime_bot_routers(self) -> None:
        included = set(dp.sub_routers)

        expected = {
            main_router,
            start_router,
            cabinet_router,
            devices_router,
            protocol_router,
            info_router,
            referrals_router,
            support_router,
            tariffs_router,
        }

        self.assertTrue(expected.issubset(included))

