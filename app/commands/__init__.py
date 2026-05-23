"""Helpers shared across command handlers."""

from __future__ import annotations

from typing import Any

from telegram import Update

from app.audit import AuditLogger


async def audit_ok(
    audit: AuditLogger,
    update: Update,
    command: str,
    *,
    profile: str | None = None,
    target: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    user = update.effective_user
    await audit.record(
        user_id=user.id if user else None,
        username=user.username if user else None,
        command=command,
        profile=profile,
        target=target,
        result="ok",
        extra=extra,
    )


async def audit_err(
    audit: AuditLogger,
    update: Update,
    command: str,
    *,
    profile: str | None = None,
    target: str | None = None,
    error: str | None = None,
) -> None:
    user = update.effective_user
    await audit.record(
        user_id=user.id if user else None,
        username=user.username if user else None,
        command=command,
        profile=profile,
        target=target,
        result="error",
        error=error,
    )


async def reply(update: Update, text: str) -> None:
    if update.effective_message is not None:
        await update.effective_message.reply_text(text)
