import unittest

from fastapi.testclient import TestClient

import landing.main as landing_main


class LandingManualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_cm = TestClient(landing_main.app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_cm.__exit__(None, None, None)

    def test_manual_page_renders_user_guide_from_documentation(self) -> None:
        response = self.client.get("/manual")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Инструкция для пользователей Amonora", response.text)
        self.assertIn("Как создать устройство", response.text)
        self.assertIn("Как подключить ключ в Happ", response.text)

    def test_manual_page_stays_hidden_from_home_navigation(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        topnav_html = response.text.split('<nav class="topnav"', 1)[1].split("</nav>", 1)[0]
        self.assertNotIn("/manual", topnav_html)

    def test_public_pages_redirect_apex_host_to_www_canonical_host(self) -> None:
        response = self.client.get(
            "/manual",
            headers={"host": "amonoraconnect.com"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 308)
        self.assertEqual(response.headers["location"], "https://www.amonoraconnect.com/manual")


if __name__ == "__main__":
    unittest.main()
