import asyncio

import httpx
import fastapi.testclient


class CompatibleTestClient:
    def __init__(self, app, base_url: str = "http://testserver", **kwargs) -> None:
        self.app = app
        self.base_url = base_url
        self.cookies = httpx.Cookies()
        self.headers = httpx.Headers(kwargs.get("headers"))

    async def _request_async(self, method: str, url: str, **kwargs):
        follow_redirects = kwargs.pop("follow_redirects", None)
        if follow_redirects is None:
            follow_redirects = method.upper() in {"GET", "HEAD", "OPTIONS"}
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=self.base_url,
            cookies=self.cookies,
            headers=self.headers,
            follow_redirects=bool(follow_redirects),
        ) as client:
            response = await client.request(method, url, **kwargs)
        self.cookies.update(response.cookies)
        return response

    def request(self, method: str, url: str, **kwargs):
        return asyncio.run(self._request_async(method, url, **kwargs))

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs):
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs):
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs):
        return self.request("DELETE", url, **kwargs)

    def close(self) -> None:
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
        return None


fastapi.testclient.TestClient = CompatibleTestClient
