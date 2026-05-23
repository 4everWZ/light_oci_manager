"""Telegram bot wiring.

Builds a python-telegram-bot ``Application`` with:

- a group=-1 authorization guard that enforces the allowlist and stops the
  update chain for unauthorized users (per spec §8.1);
- the basic-info and instance-read command handlers from ``app.commands``;
- a generic error handler that funnels exceptions into the audit log and
  surfaces a short message to the caller.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.commands import basic, instances, operations, quota
from app.commands.basic import PUBLIC_COMMANDS
from app.context import AppContext
from app.security import check, unauthorized_message

log = logging.getLogger(__name__)


def build(ctx: AppContext) -> Application:
    app = (
        Application.builder()
        .token(ctx.config.telegram.bot_token)
        .build()
    )

    # group=-1 ensures this runs before any command handler in group=0.
    app.add_handler(
        MessageHandler(filters.COMMAND, _authorize(ctx)),
        group=-1,
    )

    for handler in basic.make_handlers(ctx):
        app.add_handler(handler)
    for handler in instances.make_handlers(ctx):
        app.add_handler(handler)
    for handler in operations.make_handlers(ctx):
        app.add_handler(handler)
    for handler in quota.make_handlers(ctx):
        app.add_handler(handler)

    app.add_error_handler(_error_handler(ctx))
    return app


def _authorize(ctx: AppContext):
    async def guard(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None or not message.text:
            return
        command_name = _extract_command(message.text)
        if command_name is None:
            return
        if command_name in PUBLIC_COMMANDS:
            return

        user = update.effective_user
        decision = check(ctx.config.telegram, user.id if user else None)
        if decision.allowed:
            return

        await message.reply_text(unauthorized_message(decision.user_id))
        await ctx.audit.record(
            user_id=decision.user_id,
            username=user.username if user else None,
            command=f"/{command_name}",
            result="denied",
            error=decision.reason,
        )
        raise ApplicationHandlerStop

    return guard


def _extract_command(text: str) -> str | None:
    """Return the command name (without ``/`` or ``@botname``) or None."""
    if not text.startswith("/"):
        return None
    head = text.split()[0]
    name = head[1:]
    if "@" in name:
        name = name.split("@", 1)[0]
    return name or None


def _error_handler(ctx: AppContext):
    async def handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        log.exception("Unhandled error in handler", exc_info=context.error)
        user_id: int | None = None
        username: str | None = None
        if isinstance(update, Update) and update.effective_user is not None:
            user_id = update.effective_user.id
            username = update.effective_user.username
            if update.effective_message is not None:
                try:
                    await update.effective_message.reply_text(
                        "Internal error. Check server logs."
                    )
                except Exception:  # noqa: BLE001 - best-effort reply
                    log.exception("Failed to notify user of internal error")
        await ctx.audit.record(
            user_id=user_id,
            username=username,
            command="<error>",
            result="error",
            error=repr(context.error),
        )

    return handler
