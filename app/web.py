"""aiohttp endpoints for health and version.

Spec §5: keep the 8818 port serving HTTP so the existing Nginx
``proxy_pass http://127.0.0.1:8818;`` rule continues to work.
"""

from __future__ import annotations

from aiohttp import web

from app.context import AppContext

CTX_KEY: web.AppKey[AppContext] = web.AppKey("ctx", AppContext)


def build_app(ctx: AppContext) -> web.Application:
    app = web.Application()
    app[CTX_KEY] = ctx
    app.router.add_get("/", _index)
    app.router.add_get("/healthz", _healthz)
    app.router.add_get("/version", _version)
    return app


async def _index(request: web.Request) -> web.Response:
    ctx = request.app[CTX_KEY]
    text = (
        "oci-helper-lite-tg is running.\n"
        "Telegram bot: enabled\n"
        f"Version: {ctx.version}\n"
    )
    return web.Response(text=text, content_type="text/plain")


async def _healthz(request: web.Request) -> web.Response:
    ctx = request.app[CTX_KEY]
    return web.json_response(
        {
            "status": "ok",
            "telegram": "running",
            "profiles_loaded": len(ctx.config.oci.profiles),
        }
    )


async def _version(request: web.Request) -> web.Response:
    ctx = request.app[CTX_KEY]
    return web.json_response({"version": ctx.version})
