from __future__ import annotations

from app.config import TelegramConfig
from app.security import check, mask_fingerprint, mask_ocid, unauthorized_message


def _tcfg(ids: set[int]) -> TelegramConfig:
    return TelegramConfig(bot_token="t", allowed_user_ids=frozenset(ids))


def test_allowed_user_passes() -> None:
    d = check(_tcfg({1, 2}), 1)
    assert d.allowed is True
    assert d.user_id == 1


def test_unknown_user_denied() -> None:
    d = check(_tcfg({1, 2}), 3)
    assert d.allowed is False
    assert d.user_id == 3
    assert "allowlist" in d.reason


def test_missing_user_denied() -> None:
    d = check(_tcfg({1, 2}), None)
    assert d.allowed is False
    assert d.user_id is None


def test_unauthorized_message_includes_id() -> None:
    assert "999" in unauthorized_message(999)
    assert "unknown" in unauthorized_message(None)


def test_mask_ocid_keeps_last_chars() -> None:
    full = "ocid1.instance.oc1.iad.aaaainstance0000abcd1234"
    masked = mask_ocid(full)
    assert masked.startswith("ocid1.instance...")
    assert masked.endswith("abcd1234")
    assert full[20:30] not in masked


def test_mask_ocid_passthrough_for_non_ocid() -> None:
    assert mask_ocid("hello") == "hello"
    assert mask_ocid("") == ""


def test_mask_fingerprint() -> None:
    fp = "aa:bb:cc:dd:ee:ff:00:11:22:33"
    assert mask_fingerprint(fp) == "aa:**:33"
    assert mask_fingerprint("") == ""
    assert mask_fingerprint("nocolons") == "nocolons"
