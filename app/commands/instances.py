"""Instance read-only commands.

Spec §4.3 (/instances, /instance) and §4.5 (/public_ip).

This module is intentionally thin: it parses args, calls the OCI client,
resolves resource queries via ``resource_match``, formats output via
``formatters``, and writes one audit record per invocation.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app import resource_match
from app.audit import AuditLogger
from app.commands.basic import _reply
from app.context import AppContext
from app.formatters import (
    chunk_message,
    format_instance_summary,
    format_instances_page,
    format_ip_row,
    paginate,
)
from app.oci_client import OciApiError
from app.resource_match import AmbiguousResource, ResourceNotFound
from app.security import mask_ocid


def make_handlers(ctx: AppContext) -> list[CommandHandler]:
    return [
        CommandHandler("instances", _instances(ctx)),
        CommandHandler("instance", _instance(ctx)),
        CommandHandler("public_ip", _public_ip(ctx)),
    ]


def _instances(ctx: AppContext):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args or []
        profile_name = args[0] if args else None
        try:
            profile = ctx.config.oci.get(profile_name)
        except ValueError as exc:
            await _reply(update, str(exc))
            await _audit_err(ctx.audit, update, "/instances", error=str(exc))
            return

        try:
            instances = await ctx.oci.list_instances(profile.name)
        except OciApiError as exc:
            await _reply(update, exc.user_message())
            await _audit_err(
                ctx.audit, update, "/instances", profile=profile.name, error=str(exc)
            )
            return

        page_size = ctx.config.runtime.default_page_size
        any_sent = False
        for page in paginate(instances, page_size):
            text = format_instances_page(profile.name, profile.region, page)
            for chunk in chunk_message(text):
                await _reply(update, chunk)
                any_sent = True
        if not any_sent:
            # paginate() yields nothing when ``instances`` is empty; surface
            # the empty-state message explicitly.
            await _reply(
                update,
                format_instances_page(profile.name, profile.region, []),
            )

        await _audit_ok(
            ctx.audit,
            update,
            "/instances",
            profile=profile.name,
            extra={"count": len(instances)},
        )

    return handler


def _instance(ctx: AppContext):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args or []
        if not args:
            await _reply(
                update, "Usage: /instance <name_or_short_id> [profile]"
            )
            return
        query = args[0]
        profile_name = args[1] if len(args) > 1 else None
        try:
            profile = ctx.config.oci.get(profile_name)
        except ValueError as exc:
            await _reply(update, str(exc))
            await _audit_err(ctx.audit, update, "/instance", error=str(exc))
            return

        try:
            instances = await ctx.oci.list_instances(profile.name)
            match = resource_match.match(
                query, instances, profile=profile.name, region=profile.region
            )
        except ResourceNotFound as exc:
            await _reply(update, str(exc))
            await _audit_err(
                ctx.audit, update, "/instance", profile=profile.name, error="not_found"
            )
            return
        except AmbiguousResource as exc:
            candidates = "\n".join(
                f"{i + 1}. {c.display_name} ({mask_ocid(c.id)})"
                for i, c in enumerate(exc.candidates)
            )
            await _reply(
                update,
                f"Ambiguous instance name {query!r}.\n{candidates}\n"
                f"Use full name or short id.",
            )
            await _audit_err(
                ctx.audit, update, "/instance", profile=profile.name, error="ambiguous"
            )
            return
        except OciApiError as exc:
            await _reply(update, exc.user_message())
            await _audit_err(
                ctx.audit, update, "/instance", profile=profile.name, error=str(exc)
            )
            return

        text = format_instance_summary(1, match)
        await _reply(update, f"Profile: {profile.name}\nRegion: {profile.region}\n\n{text}")
        await _audit_ok(
            ctx.audit, update, "/instance", profile=profile.name, target=match.id
        )

    return handler


def _public_ip(ctx: AppContext):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args or []
        query = args[0] if args else None
        profile_name = args[1] if len(args) > 1 else None
        try:
            profile = ctx.config.oci.get(profile_name)
        except ValueError as exc:
            await _reply(update, str(exc))
            await _audit_err(ctx.audit, update, "/public_ip", error=str(exc))
            return

        try:
            instances = await ctx.oci.list_instances(profile.name)
        except OciApiError as exc:
            await _reply(update, exc.user_message())
            await _audit_err(
                ctx.audit, update, "/public_ip", profile=profile.name, error=str(exc)
            )
            return

        targets: list = []
        if query is None:
            targets = instances
        else:
            try:
                targets = [
                    resource_match.match(
                        query,
                        instances,
                        profile=profile.name,
                        region=profile.region,
                    )
                ]
            except ResourceNotFound as exc:
                await _reply(update, str(exc))
                await _audit_err(
                    ctx.audit,
                    update,
                    "/public_ip",
                    profile=profile.name,
                    error="not_found",
                )
                return
            except AmbiguousResource as exc:
                names = "\n".join(c.display_name for c in exc.candidates)
                await _reply(
                    update,
                    f"Ambiguous instance name {query!r}.\n{names}\n"
                    f"Use full name or short id.",
                )
                await _audit_err(
                    ctx.audit,
                    update,
                    "/public_ip",
                    profile=profile.name,
                    error="ambiguous",
                )
                return

        if not targets:
            await _reply(update, "No instances found.")
            await _audit_ok(ctx.audit, update, "/public_ip", profile=profile.name)
            return

        rows = []
        for inst in targets:
            try:
                rows.append(await ctx.oci.get_ip_info(inst, profile.name))
            except OciApiError as exc:
                rows.append(None)
                await _audit_err(
                    ctx.audit,
                    update,
                    "/public_ip",
                    profile=profile.name,
                    target=inst.id,
                    error=str(exc),
                )

        body = "\n\n".join(
            format_ip_row(row) if row is not None else "(error fetching VNIC)"
            for row in rows
        )
        text = f"Profile: {profile.name}\nRegion: {profile.region}\n\n{body}"
        for chunk in chunk_message(text):
            await _reply(update, chunk)
        await _audit_ok(
            ctx.audit,
            update,
            "/public_ip",
            profile=profile.name,
            extra={"count": len(rows)},
        )

    return handler


async def _audit_ok(
    audit: AuditLogger,
    update: Update,
    command: str,
    *,
    profile: str | None = None,
    target: str | None = None,
    extra: dict | None = None,
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


async def _audit_err(
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
