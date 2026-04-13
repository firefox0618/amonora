import unittest

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

import dashboard.main as dashboard_main


class DashboardLegacyRedirectsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.startup_handlers = list(dashboard_main.app.router.on_startup)
        dashboard_main.app.router.on_startup.clear()
        cls.client_cm = TestClient(dashboard_main.app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_cm.__exit__(None, None, None)
        dashboard_main.app.router.on_startup[:] = cls.startup_handlers

    def test_dashboard_overview_redirects_to_new_ui_route(self) -> None:
        response = self.client.get("/dashboard/overview", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/overview")

    def test_dashboard_user_detail_redirects_to_users_query_param(self) -> None:
        response = self.client.get("/dashboard/users/42?notice=ok", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        location = urlparse(response.headers["location"])
        self.assertEqual(location.path, "/users")
        self.assertEqual(parse_qs(location.query), {"notice": ["ok"], "user_id": ["42"]})

    def test_dashboard_analytics_redirects_to_new_ui_route(self) -> None:
        response = self.client.get("/dashboard/analytics?q=inst", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        location = urlparse(response.headers["location"])
        self.assertEqual(location.path, "/analytics")
        self.assertEqual(parse_qs(location.query), {"q": ["inst"]})

    def test_dashboard_support_detail_redirects_to_support_query_param(self) -> None:
        response = self.client.get("/dashboard/support/5001?filter_mode=new", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        location = urlparse(response.headers["location"])
        self.assertEqual(location.path, "/support")
        self.assertEqual(parse_qs(location.query), {"filter_mode": ["new"], "ticket_id": ["5001"]})


if __name__ == "__main__":
    unittest.main()
