from __future__ import annotations

from telegram.ext import CommandHandler

from app.commands import quota
from tests.fakes.oci_fake import FakeLimitValue
from tests.fakes.telegram_fake import FakeContext, make_update


async def _invoke(ctx, args=None, user_id=111):
    handlers = quota.make_handlers(ctx)
    cmd_handlers = [h for h in handlers if isinstance(h, CommandHandler)]
    handler = next(h for h in cmd_handlers if "quota" in h.commands)
    update = make_update(user_id=user_id)
    await handler.callback(update, FakeContext(args=args or []))
    return update


def test_aggregate_limits_sums_per_ad() -> None:
    values = [
        FakeLimitValue("standard-a1-core-count", 8, "AD-1"),
        FakeLimitValue("standard-a1-core-count", 4, "AD-2"),
        FakeLimitValue("vcn-count", 5),
    ]
    out = quota.aggregate_limits(values)
    assert out["standard-a1-core-count"] == 12
    assert out["vcn-count"] == 5


def test_compute_usage_counts_states() -> None:
    from tests.fakes.oci_fake import FakeInstance, FakeShapeConfig

    instances = [
        FakeInstance(
            id="ocid1.instance.oc1.iad.id1",
            display_name="a",
            shape_config=FakeShapeConfig(ocpus=2, memory_in_gbs=12),
        ),
        FakeInstance(
            id="ocid1.instance.oc1.iad.id2",
            display_name="b",
            lifecycle_state="STOPPED",
            shape_config=FakeShapeConfig(ocpus=1, memory_in_gbs=6),
        ),
        FakeInstance(
            id="ocid1.instance.oc1.iad.id3",
            display_name="c",
            lifecycle_state="TERMINATED",
            shape_config=None,
        ),
    ]
    usage = quota.compute_usage(instances)
    assert usage.total == 3
    assert usage.running == 1
    assert usage.stopped == 1
    assert usage.ocpus_used == 3
    assert usage.memory_used_gb == 18


async def test_quota_default_profile_shows_p1(app_ctx) -> None:
    update = await _invoke(app_ctx)
    body = "\n\n".join(update.effective_message.replies)
    assert "Profile: p1" in body
    assert "Region: ap-sydney-1" in body
    # Compute usage from the fixture: 2 instances (1 running, 1 stopped),
    # OCPUs 2, Memory 12 GB (each FakeInstance defaults to ocpus=1, mem=6).
    assert "Instances: 2" in body
    assert "OCPUs: 2" in body
    assert "Memory: 12 GB" in body
    # Aggregated limit (AD-1 + AD-2 = 8 + 4).
    assert "standard-a1-core-count: 12" in body
    # vcn limit
    assert "vcn-count: 5" in body
    # block-storage limit
    assert "total-storage-tb: 200" in body


async def test_quota_explicit_profile(app_ctx) -> None:
    update = await _invoke(app_ctx, args=["p2"])
    body = "\n".join(update.effective_message.replies)
    assert "Profile: p2" in body
    assert "Region: us-ashburn-1" in body
    # p2 fixture has compute limit but empty vcn/block-storage.
    assert "standard-a1-core-count: 1" in body
    assert "Not implemented in lite version." in body  # for vcn/block-storage


async def test_quota_unknown_profile(app_ctx) -> None:
    update = await _invoke(app_ctx, args=["missing"])
    assert "Unknown OCI profile" in update.effective_message.replies[-1]
