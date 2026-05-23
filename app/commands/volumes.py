"""Boot volume read-only commands.

Spec §13 P2: ``/boot_volumes`` — list the compartment's boot volumes
across all availability domains. Modifications (resize, terminate) are
explicitly out of scope.
"""

from __future__ import annotations

from typing import Any

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.commands import audit_err, audit_ok, reply
from app.context import AppContext
from app.formatters import chunk_message
from app.oci_client import OciApiError
from app.security import mask_ocid


def make_handlers(ctx: AppContext) -> list[CommandHandler]:
    return [CommandHandler("boot_volumes", _boot_volumes(ctx))]


def _boot_volumes(ctx: AppContext):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args or []
        profile_name = args[0] if args else None
        try:
            profile = ctx.config.oci.get(profile_name)
        except ValueError as exc:
            await reply(update, str(exc))
            await audit_err(ctx.audit, update, "/boot_volumes", error=str(exc))
            return

        try:
            volumes = await ctx.oci.list_boot_volumes(profile.name)
        except OciApiError as exc:
            await reply(update, exc.user_message())
            await audit_err(
                ctx.audit,
                update,
                "/boot_volumes",
                profile=profile.name,
                error=str(exc),
            )
            return

        text = format_boot_volumes(profile.name, profile.region, volumes)
        for chunk in chunk_message(text):
            await reply(update, chunk)
        await audit_ok(
            ctx.audit,
            update,
            "/boot_volumes",
            profile=profile.name,
            extra={"count": len(volumes), "total_gb": _total_gb(volumes)},
        )

    return handler


def format_boot_volumes(profile: str, region: str, volumes: list[Any]) -> str:
    head = [f"Profile: {profile}", f"Region: {region}"]
    if not volumes:
        head.append("")
        head.append("No boot volumes in compartment.")
        return "\n".join(head)
    head.append("")
    head.append(f"Total: {len(volumes)} ({_total_gb(volumes)} GB)")
    head.append("")
    rows = []
    for idx, vol in enumerate(volumes, start=1):
        rows.append(f"{idx}. {vol.display_name}")
        rows.append(f"   State: {vol.lifecycle_state}")
        rows.append(f"   Size: {vol.size_in_gbs} GB")
        rows.append(f"   AD: {vol.availability_domain}")
        rows.append(f"   ID: {mask_ocid(vol.id)}")
    return "\n".join(head + rows)


def _total_gb(volumes: list[Any]) -> int:
    total = 0
    for v in volumes:
        size = getattr(v, "size_in_gbs", None)
        if size is None:
            continue
        try:
            total += int(size)
        except (TypeError, ValueError):
            continue
    return total
