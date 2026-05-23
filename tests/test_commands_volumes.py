from __future__ import annotations

from telegram.ext import CommandHandler

from app.commands import volumes
from tests.fakes.telegram_fake import FakeContext, make_update


async def _invoke(ctx, args=None):
    handlers = volumes.make_handlers(ctx)
    cmd_handlers = [h for h in handlers if isinstance(h, CommandHandler)]
    handler = next(h for h in cmd_handlers if "boot_volumes" in h.commands)
    update = make_update()
    await handler.callback(update, FakeContext(args=args or []))
    return update


async def test_boot_volumes_default_profile(app_ctx) -> None:
    update = await _invoke(app_ctx)
    body = "\n".join(update.effective_message.replies)
    assert "Profile: p1" in body
    assert "Region: ap-sydney-1" in body
    assert "Total: 2 (150 GB)" in body
    assert "bv-instance-20260331-2201" in body
    assert "bv-instance-20260401-0900" in body
    assert "Size: 50 GB" in body
    assert "Size: 100 GB" in body
    # OCID masked.
    assert "ocid1.bootvolume.oc1.iad.fakebootvol001aaaa" not in body
    assert "ocid1.bootvolume..." in body


async def test_boot_volumes_empty_profile(app_ctx) -> None:
    update = await _invoke(app_ctx, args=["p2"])
    body = "\n".join(update.effective_message.replies)
    assert "No boot volumes" in body


async def test_boot_volumes_unknown_profile(app_ctx) -> None:
    update = await _invoke(app_ctx, args=["missing"])
    assert "Unknown OCI profile" in update.effective_message.replies[-1]
