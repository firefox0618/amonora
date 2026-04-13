from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class DashboardQueryPollingHardeningTests(unittest.TestCase):
    def test_visibility_aware_refetch_helper_is_used_by_queries(self) -> None:
        source = (REPO_ROOT / "dashboard/ui/src/hooks/use-dashboard.ts").read_text(encoding="utf-8")
        providers_source = (REPO_ROOT / "dashboard/ui/src/components/providers.tsx").read_text(encoding="utf-8")
        self.assertIn("function foregroundRefetchInterval(intervalMs: number, enabled = true): number | false", source)
        self.assertIn("const quietQueryDefaults = {", source)
        self.assertGreaterEqual(source.count("...quietQueryDefaults"), 11)
        self.assertIn('refetchInterval: () => foregroundRefetchInterval(30_000, enabled)', source)
        self.assertIn('refetchInterval: () => foregroundRefetchInterval(60_000)', source)
        self.assertIn('refetchInterval: () => foregroundRefetchInterval(45_000)', source)
        self.assertIn('refetchInterval: () => foregroundRefetchInterval(20_000)', source)
        self.assertIn('refetchInterval: () => foregroundRefetchInterval(30_000)', source)
        self.assertIn("refetchOnWindowFocus: false", providers_source)
        self.assertIn("refetchOnReconnect: false", providers_source)


if __name__ == "__main__":
    unittest.main()
