"""Security list read-only commands.

Spec §4.7: list security lists and dump their ingress rules. Modifying
security rules is explicitly out of scope.
"""

from __future__ import annotations

from typing import Any

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app import resource_match
from app.commands import audit_err, audit_ok, reply
from app.context import AppContext
from app.formatters import chunk_message
from app.oci_client import OciApiError
from app.resource_match import AmbiguousResource, ResourceNotFound
from app.security import mask_ocid

_PROTO_NAMES = {
    "1": "ICMP",
    "6": "TCP",
    "17": "UDP",
    "58": "ICMPv6",
    "all": "ALL",
}


def make_handlers(ctx: AppContext) -> list[CommandHandler]:
    return [
        CommandHandler("security_lists", _security_lists(ctx)),
        CommandHandler("security_list", _security_list(ctx)),
    ]


def _security_lists(ctx: AppContext):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args or []
        profile_name = args[0] if args else None
        try:
            profile = ctx.config.oci.get(profile_name)
        except ValueError as exc:
            await reply(update, str(exc))
            await audit_err(ctx.audit, update, "/security_lists", error=str(exc))
            return

        try:
            lists = await ctx.oci.list_security_lists(profile.name)
        except OciApiError as exc:
            await reply(update, exc.user_message())
            await audit_err(
                ctx.audit,
                update,
                "/security_lists",
                profile=profile.name,
                error=str(exc),
            )
            return

        text = format_security_lists(profile.name, profile.region, lists)
        for chunk in chunk_message(text):
            await reply(update, chunk)
        await audit_ok(
            ctx.audit,
            update,
            "/security_lists",
            profile=profile.name,
            extra={"count": len(lists)},
        )

    return handler


def _security_list(ctx: AppContext):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args or []
        if not args:
            await reply(
                update, "Usage: /security_list <name_or_short_id> [profile]"
            )
            return
        query = args[0]
        profile_name = args[1] if len(args) > 1 else None
        try:
            profile = ctx.config.oci.get(profile_name)
        except ValueError as exc:
            await reply(update, str(exc))
            await audit_err(ctx.audit, update, "/security_list", error=str(exc))
            return

        try:
            lists = await ctx.oci.list_security_lists(profile.name)
            match = resource_match.match(
                query, lists, profile=profile.name, region=profile.region
            )
        except ResourceNotFound as exc:
            await reply(update, str(exc))
            await audit_err(
                ctx.audit,
                update,
                "/security_list",
                profile=profile.name,
                error="not_found",
            )
            return
        except AmbiguousResource as exc:
            names = "\n".join(c.display_name for c in exc.candidates)
            await reply(
                update,
                f"Ambiguous security list {query!r}.\n{names}\nUse full name or short id.",
            )
            await audit_err(
                ctx.audit,
                update,
                "/security_list",
                profile=profile.name,
                error="ambiguous",
            )
            return
        except OciApiError as exc:
            await reply(update, exc.user_message())
            await audit_err(
                ctx.audit,
                update,
                "/security_list",
                profile=profile.name,
                error=str(exc),
            )
            return

        text = format_security_list_detail(profile.name, profile.region, match)
        for chunk in chunk_message(text):
            await reply(update, chunk)
        await audit_ok(
            ctx.audit,
            update,
            "/security_list",
            profile=profile.name,
            target=match.id,
        )

    return handler


def format_security_lists(profile: str, region: str, lists: list[Any]) -> str:
    if not lists:
        return f"Profile: {profile}\nRegion: {region}\n\nNo security lists in compartment."
    rows = [f"Profile: {profile}", f"Region: {region}", ""]
    for idx, sl in enumerate(lists, start=1):
        rules = getattr(sl, "ingress_security_rules", None) or []
        rows.append(f"{idx}. {sl.display_name}")
        rows.append(f"   ID: {mask_ocid(sl.id)}")
        rows.append(f"   Ingress rules: {len(rules)}")
    return "\n".join(rows)


def format_security_list_detail(profile: str, region: str, sl: Any) -> str:
    rules = getattr(sl, "ingress_security_rules", None) or []
    lines = [
        f"Profile: {profile}",
        f"Region: {region}",
        "",
        f"Security list: {sl.display_name}",
        f"ID: {mask_ocid(sl.id)}",
        "",
        "Ingress:",
    ]
    if not rules:
        lines.append("  (no ingress rules)")
    else:
        for rule in rules:
            lines.append(f"  - {format_ingress_rule(rule)}")
    return "\n".join(lines)


def format_ingress_rule(rule: Any) -> str:
    protocol = str(getattr(rule, "protocol", "")).lower()
    proto_name = _PROTO_NAMES.get(protocol, protocol.upper() or "?")
    source = getattr(rule, "source", "?")
    port_str = _port_string(rule, protocol)
    if port_str is None:
        return f"{proto_name} from {source}"
    return f"{proto_name} {port_str} from {source}"


def _port_string(rule: Any, protocol: str) -> str | None:
    options = None
    if protocol == "6":
        options = getattr(rule, "tcp_options", None)
    elif protocol == "17":
        options = getattr(rule, "udp_options", None)
    if options is None:
        return None
    port_range = getattr(options, "destination_port_range", None)
    if port_range is None:
        return "all"
    lo = getattr(port_range, "min", None)
    hi = getattr(port_range, "max", None)
    if lo is None or hi is None:
        return "all"
    if lo == hi:
        return str(lo)
    return f"{lo}-{hi}"
