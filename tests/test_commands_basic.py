from __future__ import annotations

import json
from pathlib import Path

from app.commands import basic
from tests.fakes.telegram_fake import FakeContext, make_update


async def _invoke(ctx, handler_name: str, args=None, user_id=111, username="tester"):
    handlers = {}
    for h in basic.make_handlers(ctx):
        for cmd in h.commands:
            handlers[cmd] = h
    handler = handlers[handler_name]
    update = make_update(user_id=user_id, username=username)
    await handler.callback(update, FakeContext(args=args or []))
    return update


async def test_status_lists_loaded_profiles(app_ctx) -> None:
    update = await _invoke(app_ctx, "status")
    text = "\n".join(update.effective_message.replies)
    assert "Default profile: p1" in text
    assert "Default region: ap-sydney-1" in text
    assert "p1" in text and "p2" in text


async def test_whoami_returns_user_id(app_ctx) -> None:
    update = await _invoke(app_ctx, "whoami", user_id=42, username="alice")
    assert update.effective_message.replies == ["Your Telegram ID: 42\nUsername: @alice"]


async def test_whoami_without_username(app_ctx) -> None:
    update = await _invoke(app_ctx, "whoami", user_id=42, username=None)
    assert update.effective_message.replies == ["Your Telegram ID: 42"]


async def test_help_returns_command_listing(app_ctx) -> None:
    update = await _invoke(app_ctx, "help")
    body = update.effective_message.replies[0]
    for cmd in ("/instances", "/instance", "/public_ip", "/whoami"):
        assert cmd in body


async def test_start_audits_event(app_ctx, tmp_path: Path) -> None:
    await _invoke(app_ctx, "start", user_id=111)
    log_path = Path(app_ctx.audit.path)
    lines = log_path.read_text().splitlines()
    assert lines
    record = json.loads(lines[-1])
    assert record["cmd"] == "/start"
    assert record["user_id"] == 111
    assert record["result"] == "ok"
