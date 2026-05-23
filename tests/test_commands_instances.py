from __future__ import annotations

import json
from pathlib import Path

from app.commands import instances
from tests.fakes.telegram_fake import FakeContext, make_update


async def _invoke(ctx, handler_name: str, args=None, user_id=111):
    handlers = {}
    for h in instances.make_handlers(ctx):
        for cmd in h.commands:
            handlers[cmd] = h
    handler = handlers[handler_name]
    update = make_update(user_id=user_id, username="tester")
    await handler.callback(update, FakeContext(args=args or []))
    return update


async def test_instances_default_profile_lists_p1(app_ctx) -> None:
    update = await _invoke(app_ctx, "instances")
    body = "\n\n".join(update.effective_message.replies)
    assert "Profile: p1" in body
    assert "instance-20260331-2201" in body
    assert "instance-20260401-0900" in body
    # p2 should not show up.
    assert "ash-vm-01" not in body


async def test_instances_with_explicit_profile(app_ctx) -> None:
    update = await _invoke(app_ctx, "instances", args=["p2"])
    body = "\n\n".join(update.effective_message.replies)
    assert "Profile: p2" in body
    assert "ash-vm-01" in body


async def test_instances_unknown_profile(app_ctx) -> None:
    update = await _invoke(app_ctx, "instances", args=["missing"])
    text = update.effective_message.replies[0]
    assert "Unknown OCI profile" in text


async def test_instances_empty_compartment(app_ctx, fake_oci) -> None:
    fake_oci._instances["p1"] = []  # type: ignore[attr-defined]
    update = await _invoke(app_ctx, "instances")
    text = update.effective_message.replies[0]
    assert "No instances" in text


async def test_instance_by_name(app_ctx) -> None:
    update = await _invoke(app_ctx, "instance", args=["instance-20260331-2201"])
    text = update.effective_message.replies[0]
    assert "instance-20260331-2201" in text
    assert "RUNNING" in text
    # Full OCID is masked.
    assert "ocid1.instance.oc1.iad.aaaainstance0000abcd1234" not in text


async def test_instance_by_short_id(app_ctx) -> None:
    update = await _invoke(app_ctx, "instance", args=["abcd1234"])
    text = update.effective_message.replies[0]
    assert "instance-20260331-2201" in text


async def test_instance_not_found(app_ctx) -> None:
    update = await _invoke(app_ctx, "instance", args=["nope"])
    text = update.effective_message.replies[0]
    assert "Resource not found" in text
    assert "p1" in text


async def test_instance_missing_arg(app_ctx) -> None:
    update = await _invoke(app_ctx, "instance", args=[])
    assert "Usage" in update.effective_message.replies[0]


async def test_public_ip_all_instances(app_ctx) -> None:
    update = await _invoke(app_ctx, "public_ip")
    body = "\n\n".join(update.effective_message.replies)
    assert "192.0.2.10" in body  # vnic for first instance
    assert "10.0.0.10" in body
    assert "Public IP: -" in body  # second instance has no public IP


async def test_public_ip_specific_instance(app_ctx) -> None:
    update = await _invoke(app_ctx, "public_ip", args=["instance-20260331-2201"])
    text = update.effective_message.replies[0]
    assert "192.0.2.10" in text


async def test_public_ip_unknown_instance(app_ctx) -> None:
    update = await _invoke(app_ctx, "public_ip", args=["nope"])
    text = update.effective_message.replies[0]
    assert "Resource not found" in text


async def test_instance_audits_target(app_ctx) -> None:
    await _invoke(app_ctx, "instance", args=["instance-20260331-2201"])
    log_path = Path(app_ctx.audit.path)
    record = json.loads(log_path.read_text().splitlines()[-1])
    assert record["cmd"] == "/instance"
    assert record["result"] == "ok"
    assert record["target"].startswith("ocid1.instance.")
