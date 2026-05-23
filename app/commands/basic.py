"""Basic informational commands.

Spec §4.1: /start /help /status /ping /whoami.

Each handler runs after the bot-level allowlist middleware in ``app.bot``,
so the allowlist is *not* re-checked here. The exception is ``/whoami``,
which is intentionally exempt from the allowlist so unknown users can
discover their Telegram ID and request access.
"""

from __future__ import annotations

import time

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.commands import audit_ok, reply
from app.context import AppContext

HELP_TEXT = (
    "Available commands:\n"
    "/start  — show bot info and your Telegram ID\n"
    "/help   — this message\n"
    "/status — service status, loaded profiles, default region\n"
    "/ping   — latency check\n"
    "/whoami — print your Telegram ID (use this to request allowlist access)\n"
    "/instances [profile] — list compute instances\n"
    "/instance <name|short-id> [profile] — show one instance\n"
    "/public_ip [name|short-id] [profile] — show public/private IPs\n"
    "/start_instance <name|short-id> [profile] — power on an instance\n"
    "/stop_instance <name|short-id> [profile] — graceful shutdown (with confirm)\n"
    "/reboot_instance <name|short-id> [profile] — graceful reboot (with confirm)\n"
    "/quota [profile] — show tenancy limits + compute usage\n"
    "/security_lists [profile] — list security lists\n"
    "/security_list <name|short-id> [profile] — show ingress rules\n"
    "/boot_volumes [profile] — list boot volumes\n"
    "/regions — list configured profile regions"
)

# Commands that bypass the allowlist. /whoami must be reachable by unknown
# users — that is its whole purpose.
PUBLIC_COMMANDS: frozenset[str] = frozenset({"whoami"})


def make_handlers(ctx: AppContext) -> list[CommandHandler]:
    return [
        CommandHandler("start", _start(ctx)),
        CommandHandler("help", _help(ctx)),
        CommandHandler("status", _status(ctx)),
        CommandHandler("ping", _ping(ctx)),
        CommandHandler("whoami", _whoami(ctx)),
    ]


def _start(ctx: AppContext):
    async def handler(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        user_id = user.id if user else None
        await reply(
            update,
            f"oci-helper-lite-tg v{ctx.version}\nYour Telegram ID: {user_id}\n\n{HELP_TEXT}",
        )
        await audit_ok(ctx.audit, update, "/start")

    return handler


def _help(ctx: AppContext):
    async def handler(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        await reply(update, HELP_TEXT)
        await audit_ok(ctx.audit, update, "/help")

    return handler


def _status(ctx: AppContext):
    async def handler(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        profiles = ", ".join(ctx.oci.profile_names) or "(none)"
        default = ctx.config.oci.default_profile
        region = ctx.config.oci.profiles[default].region
        text = (
            f"Status: ok\n"
            f"Version: {ctx.version}\n"
            f"Default profile: {default}\n"
            f"Default region: {region}\n"
            f"Loaded profiles: {profiles}"
        )
        await reply(update, text)
        await audit_ok(ctx.audit, update, "/status")

    return handler


def _ping(ctx: AppContext):
    async def handler(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        # Measure server-side handler latency. This intentionally excludes
        # Telegram round-trip; the message arrival timestamp is whatever
        # Telegram stamped, not local wall clock.
        started = time.perf_counter()
        text = f"pong ({(time.perf_counter() - started) * 1000:.1f} ms)"
        await reply(update, text)
        await audit_ok(ctx.audit, update, "/ping")

    return handler


def _whoami(ctx: AppContext):
    async def handler(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None:
            await reply(update, "Your Telegram ID: unknown")
            await audit_ok(ctx.audit, update, "/whoami")
            return
        lines = [f"Your Telegram ID: {user.id}"]
        if user.username:
            lines.append(f"Username: @{user.username}")
        await reply(update, "\n".join(lines))
        await audit_ok(ctx.audit, update, "/whoami")

    return handler


__all__ = ["HELP_TEXT", "PUBLIC_COMMANDS", "make_handlers"]
