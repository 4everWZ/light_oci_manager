"""Pending high-risk action store with TTL.

Spec §4.4 + §8.3: STOP / REBOOT (and any future modify-security-rule) must
go through a Telegram inline-button confirmation step. Each pending action
gets an opaque token that:

- is valid for ``ttl_sec`` seconds (default 60 per spec §4.2);
- can only be redeemed by the same Telegram user who created it;
- is single-use.

We keep the store entirely in-memory. A daemon restart invalidates pending
confirmations, which is the safer failure mode.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class PendingAction:
    token: str
    user_id: int
    profile: str
    instance_id: str
    instance_name: str
    action: str  # OCI instance action, e.g. "SOFTSTOP", "SOFTRESET"
    expires_at: float

    def expired(self, now: float | None = None) -> bool:
        return (now if now is not None else time.time()) >= self.expires_at


class ConfirmationStore:
    def __init__(self, ttl_sec: int) -> None:
        if ttl_sec <= 0:
            raise ValueError("ttl_sec must be positive")
        self._ttl = ttl_sec
        self._pending: dict[str, PendingAction] = {}
        self._lock = asyncio.Lock()

    @property
    def ttl_sec(self) -> int:
        return self._ttl

    async def create(
        self,
        *,
        user_id: int,
        profile: str,
        instance_id: str,
        instance_name: str,
        action: str,
    ) -> PendingAction:
        async with self._lock:
            self._sweep_locked()
            token = secrets.token_urlsafe(16)
            pending = PendingAction(
                token=token,
                user_id=user_id,
                profile=profile,
                instance_id=instance_id,
                instance_name=instance_name,
                action=action,
                expires_at=time.time() + self._ttl,
            )
            self._pending[token] = pending
            return pending

    async def take(self, token: str, user_id: int) -> PendingAction | None:
        """Return and remove the pending action iff it is valid for this user.

        Returns ``None`` when the token is unknown, expired, or owned by a
        different user.
        """
        async with self._lock:
            self._sweep_locked()
            pending = self._pending.get(token)
            if pending is None:
                return None
            if pending.user_id != user_id:
                return None
            del self._pending[token]
            return pending

    async def cancel(self, token: str, user_id: int) -> PendingAction | None:
        """Same matching rules as ``take`` but used by the explicit Cancel button."""
        return await self.take(token, user_id)

    async def size(self) -> int:
        async with self._lock:
            self._sweep_locked()
            return len(self._pending)

    def _sweep_locked(self) -> None:
        now = time.time()
        expired = [k for k, v in self._pending.items() if v.expired(now)]
        for k in expired:
            del self._pending[k]
