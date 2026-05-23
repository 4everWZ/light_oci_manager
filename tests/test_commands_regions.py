from __future__ import annotations

from telegram.ext import CommandHandler

from app.commands import regions
from tests.fakes.telegram_fake import FakeContext, make_update


async def _invoke(ctx):
    handlers = regions.make_handlers(ctx)
    handler = next(
        h for h in handlers if isinstance(h, CommandHandler) and "regions" in h.commands
    )
    update = make_update()
    await handler.callback(update, FakeContext())
    return update


async def test_regions_lists_all_profiles_with_default_marker(app_ctx) -> None:
    update = await _invoke(app_ctx)
    body = update.effective_message.replies[-1]
    assert "Configured profiles:" in body
    assert "- p1: ap-sydney-1 (default)" in body
    assert "- p2: us-ashburn-1" in body


async def test_regions_audits_count(app_ctx) -> None:
    import json
    from pathlib import Path

    await _invoke(app_ctx)
    line = Path(app_ctx.audit.path).read_text().splitlines()[-1]
    record = json.loads(line)
    assert record["cmd"] == "/regions"
    assert record["count"] == 2
