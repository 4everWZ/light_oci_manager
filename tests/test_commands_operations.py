from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from telegram.ext import CallbackQueryHandler, CommandHandler

from app.commands import operations
from tests.fakes.telegram_fake import FakeContext, make_callback_update, make_update


def _handler_index(handlers):
    cmd_index = {}
    callback = None
    for h in handlers:
        if isinstance(h, CommandHandler):
            for cmd in h.commands:
                cmd_index[cmd] = h
        elif isinstance(h, CallbackQueryHandler):
            callback = h
    return cmd_index, callback


async def _run_command(ctx, cmd_name, args=None, user_id=111):
    cmd_index, _ = _handler_index(operations.make_handlers(ctx))
    h = cmd_index[cmd_name]
    update = make_update(user_id=user_id)
    await h.callback(update, FakeContext(args=args or []))
    return update


async def _run_callback(ctx, data, user_id=111):
    _, cb = _handler_index(operations.make_handlers(ctx))
    update = make_callback_update(data=data, user_id=user_id)
    await cb.callback(update, FakeContext())
    return update


# ------------------------------------------------------------------ /start_instance


async def test_start_instance_runs_immediately(app_ctx, fake_oci) -> None:
    update = await _run_command(
        app_ctx, "start_instance", args=["instance-20260401-0900"]
    )
    text = update.effective_message.replies[-1]
    assert "Starting instance-20260401-0900" in text
    # Action was issued to the OCI fake.
    assert fake_oci.instance_action_calls == [
        ("ocid1.instance.oc1.iad.aaaainstance0000efgh5678", "START", "p1"),
    ]


async def test_start_instance_unknown(app_ctx, fake_oci) -> None:
    update = await _run_command(app_ctx, "start_instance", args=["nope"])
    text = update.effective_message.replies[-1]
    assert "Resource not found" in text
    assert fake_oci.instance_action_calls == []


async def test_start_instance_missing_arg(app_ctx) -> None:
    update = await _run_command(app_ctx, "start_instance", args=[])
    assert "Usage" in update.effective_message.replies[-1]


# --------------------------------------------------------------- confirmation flow


async def test_stop_instance_asks_for_confirmation(app_ctx, fake_oci) -> None:
    update = await _run_command(
        app_ctx, "stop_instance", args=["instance-20260331-2201"]
    )
    # No action issued yet.
    assert fake_oci.instance_action_calls == []
    text = update.effective_message.replies[-1]
    assert "Confirm SOFTSTOP" in text
    markup = update.effective_message.reply_markups[-1]
    assert markup is not None
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert {b.text for b in buttons} == {"Confirm Stop", "Cancel"}
    # Exactly one pending action stored.
    assert await app_ctx.confirmations.size() == 1


async def test_confirm_button_executes_action(app_ctx, fake_oci) -> None:
    await _run_command(app_ctx, "stop_instance", args=["instance-20260331-2201"])
    confirm_data = _extract_confirm_token(app_ctx, prefix=operations.CALLBACK_CONFIRM)
    cb_update = await _run_callback(app_ctx, data=confirm_data)
    assert cb_update.callback_query.edited_text is not None
    assert "SOFTSTOP accepted" in cb_update.callback_query.edited_text
    assert fake_oci.instance_action_calls == [
        ("ocid1.instance.oc1.iad.aaaainstance0000abcd1234", "SOFTSTOP", "p1"),
    ]
    # Token consumed.
    assert await app_ctx.confirmations.size() == 0


async def test_cancel_button_does_not_execute(app_ctx, fake_oci) -> None:
    await _run_command(app_ctx, "stop_instance", args=["instance-20260331-2201"])
    cancel_data = _extract_confirm_token(app_ctx, prefix=operations.CALLBACK_CANCEL)
    cb_update = await _run_callback(app_ctx, data=cancel_data)
    assert "Cancelled SOFTSTOP" in cb_update.callback_query.edited_text
    assert fake_oci.instance_action_calls == []
    assert await app_ctx.confirmations.size() == 0


async def test_confirm_token_user_mismatch_rejected(app_ctx, fake_oci) -> None:
    # Allowlist contains 111 and 222; pending action belongs to 111.
    await _run_command(
        app_ctx, "stop_instance", args=["instance-20260331-2201"], user_id=111
    )
    confirm_data = _extract_confirm_token(app_ctx, prefix=operations.CALLBACK_CONFIRM)
    cb_update = await _run_callback(app_ctx, data=confirm_data, user_id=222)
    assert "expired" in cb_update.callback_query.edited_text.lower() or \
        "not valid" in cb_update.callback_query.edited_text.lower()
    assert fake_oci.instance_action_calls == []


async def test_confirm_from_non_allowlisted_user_rejected(app_ctx, fake_oci) -> None:
    await _run_command(
        app_ctx, "stop_instance", args=["instance-20260331-2201"], user_id=111
    )
    confirm_data = _extract_confirm_token(app_ctx, prefix=operations.CALLBACK_CONFIRM)
    cb_update = await _run_callback(app_ctx, data=confirm_data, user_id=999)
    assert "Unauthorized" in cb_update.callback_query.edited_text
    assert fake_oci.instance_action_calls == []


async def test_reboot_instance_uses_softreset(app_ctx, fake_oci) -> None:
    await _run_command(
        app_ctx, "reboot_instance", args=["instance-20260331-2201"]
    )
    confirm_data = _extract_confirm_token(app_ctx, prefix=operations.CALLBACK_CONFIRM)
    cb_update = await _run_callback(app_ctx, data=confirm_data)
    assert "SOFTRESET accepted" in cb_update.callback_query.edited_text
    assert fake_oci.instance_action_calls == [
        ("ocid1.instance.oc1.iad.aaaainstance0000abcd1234", "SOFTRESET", "p1"),
    ]


async def test_expired_confirmation_rejected(app_ctx) -> None:
    from app.confirmations import ConfirmationStore

    # Replace with a 0.05-second TTL store; we expire by sleeping a tick.
    short_store = ConfirmationStore(ttl_sec=1)
    object.__setattr__(app_ctx, "confirmations", short_store)
    await _run_command(app_ctx, "stop_instance", args=["instance-20260331-2201"])
    pending = next(iter(short_store._pending.values()))  # type: ignore[attr-defined]
    # Manually expire.
    object.__setattr__(pending, "expires_at", 0.0)
    confirm_data = f"{operations.CALLBACK_CONFIRM}{pending.token}"
    cb_update = await _run_callback(app_ctx, data=confirm_data)
    assert "expired" in cb_update.callback_query.edited_text.lower() or \
        "not valid" in cb_update.callback_query.edited_text.lower()


async def test_audit_records_for_stop_flow(app_ctx) -> None:
    await _run_command(app_ctx, "stop_instance", args=["instance-20260331-2201"])
    confirm_data = _extract_confirm_token(app_ctx, prefix=operations.CALLBACK_CONFIRM)
    await _run_callback(app_ctx, data=confirm_data)
    log_path = Path(app_ctx.audit.path)
    lines = log_path.read_text().splitlines()
    cmds = [json.loads(line)["cmd"] for line in lines]
    assert "/stop_instance:request" in cmds
    assert "callback:confirm" in cmds


# ----------------------------------------------------------------- helpers


def _extract_confirm_token(app_ctx, *, prefix: str) -> str:
    # Pending action store contains exactly one token at this point in tests.
    tokens = list(app_ctx.confirmations._pending)  # type: ignore[attr-defined]
    assert len(tokens) == 1, f"expected one pending token, got {tokens}"
    return f"{prefix}{tokens[0]}"


# Avoid the asyncio.sleep import warning.
_ = asyncio
_ = re
