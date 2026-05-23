from __future__ import annotations

from aiohttp.test_utils import TestClient, TestServer

from app import web as web_module


async def test_index_returns_text(app_ctx) -> None:
    app = web_module.build_app(app_ctx)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/")
        assert resp.status == 200
        body = await resp.text()
        assert "oci-helper-lite-tg" in body
        assert "0.1.0-test" in body


async def test_healthz_returns_status_ok(app_ctx) -> None:
    app = web_module.build_app(app_ctx)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/healthz")
        assert resp.status == 200
        data = await resp.json()
        assert data == {"status": "ok", "telegram": "running", "profiles_loaded": 2}


async def test_version_returns_version(app_ctx) -> None:
    app = web_module.build_app(app_ctx)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/version")
        assert resp.status == 200
        data = await resp.json()
        assert data == {"version": "0.1.0-test"}
