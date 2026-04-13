import unittest

from test_bot.device_binding import activate_test_profile_device, get_test_profile_runtime


class TestBotDeviceBindingTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_runtime_for_static_profile_has_no_transfer(self) -> None:
        runtime = await get_test_profile_runtime("de_android")

        self.assertIsNotNone(runtime)
        assert runtime is not None
        self.assertFalse(runtime.supports_transfer)
        self.assertIsNone(runtime.active_device_label)
        self.assertIn("vless://", runtime.link)

    async def test_activate_static_profile_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "переключение устройства не поддерживается"):
            await activate_test_profile_device("de_android", "windows", actor_telegram_id=7650618403)


if __name__ == "__main__":
    unittest.main()
