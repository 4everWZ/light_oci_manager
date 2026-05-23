"""Instance lifecycle commands.

Spec §4.4 / §8.3: ``/start_instance`` runs immediately (low-risk power-on).
``/stop_instance`` and ``/reboot_instance`` show a Telegram inline-button
confirmation; the actual OCI action only fires when the issuing user clicks
"Confirm" within the configured TTL.

Default OCI actions for stop/reboot are the *graceful* variants
(``SOFTSTOP`` / ``SOFTRESET``) because the spec uses bare "stop" / "reboot"
and graceful shutdown is the safer interpretation. See
``docs/tradeoffs.md`` T-001.
"""

from __future__ import annotations

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from app import resource_match
from app.commands import audit_err, audit_ok, reply
from app.confirmations import PendingAction
from app.context import AppContext
from app.oci_client import OciApiError
from app.resource_match import AmbiguousResource, ResourceNotFound
from app.security import check, mask_ocid

START_ACTION = "START"
STOP_ACTION = "SOFTSTOP"
REBOOT_ACTION = "SOFTRESET"

CALLBACK_NAMESPACE = "cf"
CALLBACK_CONFIRM = f"{CALLBACK_NAMESPACE}:confirm:"
CALLBACK_CANCEL = f"{CALLBACK_NAMESPACE}:cancel:"


def make_handlers(ctx: AppContext) -> list:
    return [
        CommandHandler("start_instance", _start_instance(ctx)),
        CommandHandler("stop_instance", _confirm_command(ctx, STOP_ACTION, "Stop")),
        CommandHandler("reboot_instance", _confirm_command(ctx, REBOOT_ACTION, "Reboot")),
        CallbackQueryHandler(_callback(ctx), pattern=rf"^{CALLBACK_NAMESPACE}:"),
    ]


def _start_instance(ctx: AppContext):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        target = await _resolve(ctx, update, context.args or [], command="/start_instance")
        if target is None:
            return
        profile, instance = target
        try:
            await ctx.oci.instance_action(instance.id, START_ACTION, profile.name)
        except OciApiError as exc:
            await reply(update, exc.user_message())
            await audit_err(
                ctx.audit,
                update,
                "/start_instance",
                profile=profile.name,
                target=instance.id,
                error=str(exc),
            )
            return
        await reply(
            update,
            f"Starting {instance.display_name} (profile {profile.name})...",
        )
        await audit_ok(
            ctx.audit,
            update,
            "/start_instance",
            profile=profile.name,
            target=instance.id,
            extra={"action": START_ACTION},
        )

    return handler


def _confirm_command(ctx: AppContext, oci_action: str, label: str):
    """Build a handler that asks for inline-button confirmation before acting."""
    command_name = "/stop_instance" if oci_action == STOP_ACTION else "/reboot_instance"

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        target = await _resolve(ctx, update, context.args or [], command=command_name)
        if target is None:
            return
        profile, instance = target
        user = update.effective_user
        if user is None:
            await reply(update, "Cannot identify caller.")
            return

        pending = await ctx.confirmations.create(
            user_id=user.id,
            profile=profile.name,
            instance_id=instance.id,
            instance_name=instance.display_name,
            action=oci_action,
        )
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        f"Confirm {label}",
                        callback_data=f"{CALLBACK_CONFIRM}{pending.token}",
                    ),
                    InlineKeyboardButton(
                        "Cancel",
                        callback_data=f"{CALLBACK_CANCEL}{pending.token}",
                    ),
                ]
            ]
        )
        text = (
            f"Confirm {oci_action} instance?\n"
            f"Name: {instance.display_name}\n"
            f"Region: {profile.region}\n"
            f"ID: {mask_ocid(instance.id)}\n"
            f"(Expires in {ctx.confirmations.ttl_sec}s)"
        )
        if update.effective_message is not None:
            await update.effective_message.reply_text(text, reply_markup=keyboard)
        await audit_ok(
            ctx.audit,
            update,
            f"{command_name}:request",
            profile=profile.name,
            target=instance.id,
            extra={"token": pending.token, "action": oci_action},
        )

    return handler


def _callback(ctx: AppContext):
    async def handler(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or not query.data:
            return
        await query.answer()
        user = query.from_user
        user_id = user.id if user is not None else None

        # Defense in depth: callback events bypass the message-level
        # allowlist guard, so re-check here. Token-user binding catches
        # most cases on its own, but verifying allowlist first lets us
        # log denials consistently.
        decision = check(ctx.config.telegram, user_id)
        if not decision.allowed:
            await query.edit_message_text(
                "Unauthorized.\n"
                f"Your Telegram ID: {user_id if user_id is not None else 'unknown'}"
            )
            await audit_err(
                ctx.audit,
                update,
                "callback",
                error=decision.reason or "denied",
            )
            return

        data = query.data
        if data.startswith(CALLBACK_CONFIRM):
            token = data[len(CALLBACK_CONFIRM):]
            pending = await ctx.confirmations.take(token, user_id)  # type: ignore[arg-type]
            if pending is None:
                await query.edit_message_text(
                    "Confirmation expired or not valid for this user."
                )
                await audit_err(
                    ctx.audit,
                    update,
                    "callback:confirm",
                    error="expired_or_invalid",
                )
                return
            await _execute_pending(ctx, update, pending)
            return

        if data.startswith(CALLBACK_CANCEL):
            token = data[len(CALLBACK_CANCEL):]
            pending = await ctx.confirmations.cancel(token, user_id)  # type: ignore[arg-type]
            if pending is None:
                await query.edit_message_text(
                    "Nothing to cancel (already expired or not yours)."
                )
                return
            await query.edit_message_text(
                f"Cancelled {pending.action} on {pending.instance_name}."
            )
            await audit_ok(
                ctx.audit,
                update,
                "callback:cancel",
                profile=pending.profile,
                target=pending.instance_id,
                extra={"action": pending.action},
            )
            return

    return handler


async def _execute_pending(
    ctx: AppContext, update: Update, pending: PendingAction
) -> None:
    query = update.callback_query
    try:
        await ctx.oci.instance_action(
            pending.instance_id, pending.action, pending.profile
        )
    except OciApiError as exc:
        if query is not None:
            await query.edit_message_text(exc.user_message())
        await audit_err(
            ctx.audit,
            update,
            "callback:confirm",
            profile=pending.profile,
            target=pending.instance_id,
            error=str(exc),
        )
        return
    if query is not None:
        await query.edit_message_text(
            f"{pending.action} accepted for {pending.instance_name}."
        )
    await audit_ok(
        ctx.audit,
        update,
        "callback:confirm",
        profile=pending.profile,
        target=pending.instance_id,
        extra={"action": pending.action},
    )


async def _resolve(
    ctx: AppContext,
    update: Update,
    args: list[str],
    *,
    command: str,
):
    """Parse args, resolve to an instance, or reply with an error message."""
    if not args:
        await reply(update, f"Usage: {command} <name_or_short_id> [profile]")
        return None
    query = args[0]
    profile_name = args[1] if len(args) > 1 else None
    try:
        profile = ctx.config.oci.get(profile_name)
    except ValueError as exc:
        await reply(update, str(exc))
        await audit_err(ctx.audit, update, command, error=str(exc))
        return None
    try:
        instances = await ctx.oci.list_instances(profile.name)
        match = resource_match.match(
            query, instances, profile=profile.name, region=profile.region
        )
    except ResourceNotFound as exc:
        await reply(update, str(exc))
        await audit_err(
            ctx.audit, update, command, profile=profile.name, error="not_found"
        )
        return None
    except AmbiguousResource as exc:
        names = "\n".join(c.display_name for c in exc.candidates)
        await reply(
            update,
            f"Ambiguous instance name {query!r}.\n{names}\nUse full name or short id.",
        )
        await audit_err(
            ctx.audit, update, command, profile=profile.name, error="ambiguous"
        )
        return None
    except OciApiError as exc:
        await reply(update, exc.user_message())
        await audit_err(
            ctx.audit, update, command, profile=profile.name, error=str(exc)
        )
        return None
    return profile, match
