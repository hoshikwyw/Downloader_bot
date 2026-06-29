"""Tiny HTTP health server for hosts that require a bound port (e.g. Render).

Render's free *web* services must listen on $PORT and spin down after ~15 min of
no inbound traffic. Our bot uses outbound long polling, so we expose a trivial
endpoint here that an external uptime pinger can hit to keep the service awake.

When PORT is unset (local laptop runs), this does nothing.
"""
from __future__ import annotations

import logging
import os

from aiohttp import web

logger = logging.getLogger("downloader-bot")


async def _ok(_request: web.Request) -> web.Response:
    return web.Response(text="ok")


async def start_health_server() -> web.AppRunner | None:
    port_raw = os.getenv("PORT")
    if not port_raw:
        return None  # not a hosted web service — skip

    app = web.Application()
    app.router.add_get("/", _ok)
    app.router.add_get("/health", _ok)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(port_raw))
    await site.start()
    logger.info("Health server listening on :%s (/health)", port_raw)
    return runner
