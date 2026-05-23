"""Quota / limits command.

Spec §4.6: show core resources for the chosen profile. We compute compute
usage locally from ``list_instances`` and ask the OCI Limits API for the
declared limits for the compute, vcn, and block-storage services. AD-scoped
limits are summed so the user sees one number per limit name.

Per spec, missing fields render as ``Not implemented in lite version.``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.commands import audit_err, audit_ok, reply
from app.context import AppContext
from app.formatters import chunk_message
from app.oci_client import OciApiError

QUOTA_SERVICES: tuple[str, ...] = ("compute", "vcn", "block-storage")


@dataclass
class ComputeUsage:
    total: int
    running: int
    stopped: int
    ocpus_used: float
    memory_used_gb: float


def make_handlers(ctx: AppContext) -> list[CommandHandler]:
    return [CommandHandler("quota", _quota(ctx))]


def _quota(ctx: AppContext):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args or []
        profile_name = args[0] if args else None
        try:
            profile = ctx.config.oci.get(profile_name)
        except ValueError as exc:
            await reply(update, str(exc))
            await audit_err(ctx.audit, update, "/quota", error=str(exc))
            return

        try:
            instances = await ctx.oci.list_instances(profile.name)
        except OciApiError as exc:
            await reply(update, exc.user_message())
            await audit_err(
                ctx.audit, update, "/quota", profile=profile.name, error=str(exc)
            )
            return

        usage = compute_usage(instances)

        limits_by_service: dict[str, dict[str, float]] = {}
        for service in QUOTA_SERVICES:
            try:
                values = await ctx.oci.list_limit_values(service, profile.name)
            except OciApiError as exc:
                # Per spec §9 we keep the rest of the report and annotate
                # the failed service inline rather than aborting.
                limits_by_service[service] = {"_error": exc.user_message()}
                continue
            limits_by_service[service] = aggregate_limits(values)

        text = format_quota(profile.name, profile.region, usage, limits_by_service)
        for chunk in chunk_message(text):
            await reply(update, chunk)
        await audit_ok(
            ctx.audit,
            update,
            "/quota",
            profile=profile.name,
            extra={"services": list(limits_by_service.keys())},
        )

    return handler


def compute_usage(instances: list[Any]) -> ComputeUsage:
    total = len(instances)
    running = sum(1 for i in instances if i.lifecycle_state == "RUNNING")
    stopped = sum(1 for i in instances if i.lifecycle_state == "STOPPED")
    ocpus = 0.0
    memory = 0.0
    for inst in instances:
        cfg = getattr(inst, "shape_config", None)
        if cfg is None:
            continue
        if getattr(cfg, "ocpus", None) is not None:
            ocpus += float(cfg.ocpus)
        if getattr(cfg, "memory_in_gbs", None) is not None:
            memory += float(cfg.memory_in_gbs)
    return ComputeUsage(
        total=total,
        running=running,
        stopped=stopped,
        ocpus_used=ocpus,
        memory_used_gb=memory,
    )


def aggregate_limits(values: list[Any]) -> dict[str, float]:
    """Sum limit values across availability domains, keyed by limit name.

    OCI returns one record per (limit name, AD) for AD-scoped limits. The
    user really wants the per-region total, so we add them up.
    """
    out: dict[str, float] = {}
    for v in values:
        name = getattr(v, "name", None)
        value = getattr(v, "value", None)
        if name is None or value is None:
            continue
        out[name] = out.get(name, 0) + float(value)
    return out


def format_quota(
    profile: str,
    region: str,
    usage: ComputeUsage,
    limits_by_service: dict[str, dict[str, float]],
) -> str:
    lines = [
        f"Profile: {profile}",
        f"Region: {region}",
        "",
        "Compute (used):",
        f"  Instances: {usage.total} (running: {usage.running}, stopped: {usage.stopped})",
        f"  OCPUs: {_fmt_num(usage.ocpus_used)}",
        f"  Memory: {_fmt_num(usage.memory_used_gb)} GB",
    ]
    for service in QUOTA_SERVICES:
        lines.append("")
        lines.append(f"Limits — {service}:")
        entries = limits_by_service.get(service, {})
        if "_error" in entries:
            lines.append(f"  (error) {entries['_error']}")
            continue
        if not entries:
            lines.append("  Not implemented in lite version.")
            continue
        for name in sorted(entries):
            lines.append(f"  - {name}: {_fmt_num(entries[name])}")
    return "\n".join(lines)


def _fmt_num(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}"
