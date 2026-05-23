"""/regions — list configured profile regions.

Spec §13 P2: surface the regions of every configured OCI profile so the
caller can see at a glance which regions this bot can act on without
having to read config.yml. No OCI API call needed.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.commands import audit_ok, reply
from app.context import AppContext


def make_handlers(ctx: AppContext) -> list[CommandHandler]:
    return [CommandHandler("regions", _regions(ctx))]


def _regions(ctx: AppContext):
    async def handler(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        default = ctx.config.oci.default_profile
        lines = ["Configured profiles:"]
        for name in sorted(ctx.config.oci.profiles):
            profile = ctx.config.oci.profiles[name]
            tag = " (default)" if name == default else ""
            lines.append(f"- {name}: {profile.region}{tag}")
        await reply(update, "\n".join(lines))
        await audit_ok(
            ctx.audit,
            update,
            "/regions",
            extra={"count": len(ctx.config.oci.profiles)},
        )

    return handler
