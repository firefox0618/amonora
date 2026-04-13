import unittest

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class DashboardUiProxyHeaderTests(unittest.TestCase):
    def test_proxy_route_forwards_public_host_and_proto(self) -> None:
        source = (REPO_ROOT / "dashboard/ui/src/app/api/proxy/[...path]/route.ts").read_text(encoding="utf-8")

        self.assertIn('headers.set("x-forwarded-host", publicHost);', source)
        self.assertIn('headers.set("x-forwarded-proto", publicProto);', source)


if __name__ == "__main__":
    unittest.main()
