import unittest

from unittest.mock import AsyncMock, patch

from dashboard.services import get_documentation_page


class DashboardKnowledgeSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_documentation_page_sanitizes_dangerous_html(self) -> None:
        manifest = {
            "title": "Docs",
            "description": "Knowledge",
            "sections": [
                {
                    "title": "Security",
                    "items": [
                        {
                            "slug": "security-test",
                            "title": "Security test",
                            "summary": "Summary",
                            "github_url": "https://example.com/repo/security-test.md",
                            "raw_url": "https://example.com/raw/security-test.md",
                        }
                    ],
                }
            ],
            "total_docs": 1,
        }
        markdown_text = (
            "# Заголовок\n\n"
            '[Безопасная ссылка](https://example.com/docs)\n\n'
            '<script>alert(\"boom\")</script>\n'
            '<img src=\"x\" onerror=\"alert(1)\">\n'
            '<a href=\"javascript:alert(1)\">bad link</a>\n'
        )

        with (
            patch("dashboard.services.get_documentation_manifest", new=AsyncMock(return_value=manifest)),
            patch("dashboard.services._get_document_text", new=AsyncMock(return_value=(markdown_text, "local"))),
        ):
            page = await get_documentation_page("security-test")

        html = str(page["current"]["html"])
        self.assertIn("<h1", html)
        self.assertIn("https://example.com/docs", html)
        self.assertNotIn("<script", html.lower())
        self.assertNotIn("onerror", html.lower())
        self.assertNotIn("javascript:", html.lower())
        self.assertIn("<img", html.lower())


if __name__ == "__main__":
    unittest.main()
