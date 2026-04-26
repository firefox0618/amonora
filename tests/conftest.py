import asyncio
import inspect

import httpx
import fastapi.testclient
import pytest


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
collect_ignore = ["test_db.py"]


def pytest_collection_modifyitems(items) -> None:
    for item in items:
        test_obj = getattr(item, "obj", None)
        if test_obj is not None and inspect.iscoroutinefunction(test_obj):
            item.add_marker(pytest.mark.anyio)


def pytest_pyfunc_call(pyfuncitem) -> bool | None:
    test_obj = getattr(pyfuncitem, "obj", None)
    if test_obj is None or not inspect.iscoroutinefunction(test_obj):
        return None
    funcargs = {name: pyfuncitem.funcargs[name] for name in pyfuncitem._fixtureinfo.argnames}
    asyncio.run(test_obj(**funcargs))
    return True
