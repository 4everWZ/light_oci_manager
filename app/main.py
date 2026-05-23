"""Process entrypoint.

Wires config + audit + OCI client into an ``AppContext`` and runs both the
Telegram bot (long-polling) and the aiohttp health server inside the same
asyncio event loop. Shutdown is driven by SIGINT/SIGTERM.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from aiohttp import web

from app import bot, config
from app import web as web_module
from app.audit import AuditLogger
from app.confirmations import ConfirmationStore
from app.context import AppContext
from app.oci_client import OciClient

DEFAULT_CONFIG_PATH = "/app/oci-helper/config.yml"
VERSION = "0.1.0"

log = logging.getLogger("oci-helper-lite-tg")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="oci-helper-lite-tg")
    parser.add_argument(
        "--config",
        default=os.environ.get("OCI_HELPER_CONFIG", DEFAULT_CONFIG_PATH),
        help="Path to config.yml (default: %(default)s)",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("OCI_HELPER_LOG_LEVEL", "INFO"),
        help="Logging level (default: %(default)s)",
    )
    return parser.parse_args(argv)


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    # python-telegram-bot is chatty at DEBUG.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext.Application").setLevel(logging.INFO)


async def _run(cfg_path: Path) -> int:
    try:
        cfg = config.load(cfg_path)
    except config.ConfigError as exc:
        log.error("Config error: %s", exc)
        return 2

    audit = AuditLogger(cfg.runtime.audit_log)
    oci_client = OciClient(cfg.oci)
    confirmations = ConfirmationStore(ttl_sec=cfg.runtime.confirmation_ttl_sec)
    ctx = AppContext(
        config=cfg,
        oci=oci_client,
        audit=audit,
        confirmations=confirmations,
        version=VERSION,
    )

    telegram_app = bot.build(ctx)
    web_app = web_module.build_app(ctx)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, cfg.server.host, cfg.server.port)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # pragma: no cover - Windows
            signal.signal(sig, lambda *_: stop.set())

    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling(drop_pending_updates=True)
    await site.start()
    log.info(
        "Started: bot=running, http=%s:%d, profiles=%d",
        cfg.server.host,
        cfg.server.port,
        len(cfg.oci.profiles),
    )

    try:
        await stop.wait()
    finally:
        log.info("Shutting down")
        await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()
        await runner.cleanup()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    _configure_logging(args.log_level)
    return asyncio.run(_run(Path(args.config)))


if __name__ == "__main__":
    raise SystemExit(main())
