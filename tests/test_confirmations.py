from __future__ import annotations

import asyncio
import time

import pytest

from app.confirmations import ConfirmationStore


@pytest.mark.asyncio
async def test_create_and_take_round_trip() -> None:
    store = ConfirmationStore(ttl_sec=60)
    pending = await store.create(
        user_id=1,
        profile="p1",
        instance_id="ocid1.instance.oc1.iad.id1",
        instance_name="vm",
        action="SOFTSTOP",
    )
    assert pending.token
    assert await store.size() == 1
    taken = await store.take(pending.token, user_id=1)
    assert taken is not None
    assert taken.token == pending.token
    assert await store.size() == 0


@pytest.mark.asyncio
async def test_take_wrong_user_returns_none() -> None:
    store = ConfirmationStore(ttl_sec=60)
    pending = await store.create(
        user_id=1,
        profile="p1",
        instance_id="i",
        instance_name="vm",
        action="SOFTSTOP",
    )
    assert await store.take(pending.token, user_id=2) is None
    # Token still present, can be redeemed by owner.
    assert await store.take(pending.token, user_id=1) is not None


@pytest.mark.asyncio
async def test_take_unknown_token_returns_none() -> None:
    store = ConfirmationStore(ttl_sec=60)
    assert await store.take("not-a-real-token", user_id=1) is None


@pytest.mark.asyncio
async def test_expired_token_is_purged() -> None:
    store = ConfirmationStore(ttl_sec=1)
    pending = await store.create(
        user_id=1,
        profile="p1",
        instance_id="i",
        instance_name="vm",
        action="STOP",
    )
    # Force-expire by mutating the frozen dataclass via object.__setattr__.
    object.__setattr__(pending, "expires_at", time.time() - 1)
    assert await store.take(pending.token, user_id=1) is None
    assert await store.size() == 0


def test_invalid_ttl_rejected() -> None:
    with pytest.raises(ValueError):
        ConfirmationStore(ttl_sec=0)
    with pytest.raises(ValueError):
        ConfirmationStore(ttl_sec=-5)


@pytest.mark.asyncio
async def test_concurrent_creates_have_unique_tokens() -> None:
    store = ConfirmationStore(ttl_sec=60)
    pendings = await asyncio.gather(
        *(
            store.create(
                user_id=i,
                profile="p",
                instance_id=f"i{i}",
                instance_name=f"vm-{i}",
                action="SOFTSTOP",
            )
            for i in range(50)
        )
    )
    tokens = {p.token for p in pendings}
    assert len(tokens) == 50
