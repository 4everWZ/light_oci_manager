"""Security primitives: allowlist enforcement and OCID masking.

Spec references:
- §8.1 allowlist
- §8.2 sensitive value masking
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import TelegramConfig

OCID_RE = re.compile(r"^ocid1\.[a-z0-9]+\.[a-z0-9-]*\.[a-z0-9-]*\.[a-z0-9]+$")


@dataclass(frozen=True)
class AuthDecision:
    allowed: bool
    user_id: int | None
    reason: str = ""


def check(telegram: TelegramConfig, user_id: int | None) -> AuthDecision:
    """Pure decision function used by the bot middleware and tests."""
    if user_id is None:
        return AuthDecision(allowed=False, user_id=None, reason="missing user_id")
    if user_id in telegram.allowed_user_ids:
        return AuthDecision(allowed=True, user_id=user_id)
    return AuthDecision(allowed=False, user_id=user_id, reason="not in allowlist")


def unauthorized_message(user_id: int | None) -> str:
    """User-facing rejection. Spec §8.1 mandates surfacing the caller's ID."""
    if user_id is None:
        return "Unauthorized.\nYour Telegram ID: unknown"
    return f"Unauthorized.\nYour Telegram ID: {user_id}"


def mask_ocid(ocid: str, *, suffix: int = 8) -> str:
    """Return a short, safe form of an OCID for Telegram output.

    Examples:
        >>> mask_ocid("ocid1.instance.oc1.iad.abcdefghijklmnop")
        'ocid1.instance...lmnop'
    """
    if not ocid:
        return ocid
    if not OCID_RE.match(ocid):
        # Not an OCID — return as-is. The caller is responsible for not passing
        # secrets here.
        return ocid
    head, _, _ = ocid.partition(".")
    kind = ocid.split(".")[1] if "." in ocid else ""
    tail = ocid[-suffix:] if len(ocid) > suffix else ocid
    return f"{head}.{kind}...{tail}"


def mask_fingerprint(fp: str) -> str:
    """Mask all but the first and last colon-separated octet of a fingerprint."""
    if not fp or ":" not in fp:
        return fp
    parts = fp.split(":")
    if len(parts) <= 2:
        return fp
    return f"{parts[0]}:**:{parts[-1]}"
