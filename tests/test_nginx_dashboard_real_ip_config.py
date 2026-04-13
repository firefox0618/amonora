from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class DashboardNginxRealIpConfigTests(unittest.TestCase):
    def test_dashboard_nginx_trusts_cloudflare_real_ip_ranges(self) -> None:
        source = (REPO_ROOT / "ops/nginx/amonora-dashboard.server.conf").read_text(encoding="utf-8")
        self.assertIn("real_ip_header CF-Connecting-IP;", source)
        self.assertIn("real_ip_recursive on;", source)
        self.assertIn("set_real_ip_from 173.245.48.0/20;", source)
        self.assertIn("set_real_ip_from 104.16.0.0/13;", source)
        self.assertIn("set_real_ip_from 2400:cb00::/32;", source)
        self.assertIn("set_real_ip_from 2a06:98c0::/29;", source)

    def test_dashboard_nginx_sets_dedicated_trusted_client_ip_header(self) -> None:
        source = (REPO_ROOT / "ops/nginx/amonora-dashboard.server.conf").read_text(encoding="utf-8")
        self.assertIn("proxy_set_header X-Amonora-Client-IP $remote_addr;", source)


if __name__ == "__main__":
    unittest.main()
