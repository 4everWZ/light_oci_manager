"""Test doubles for telegram Update/Context."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FakeUser:
    id: int
    username: str | None = None


class FakeMessage:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


@dataclass
class FakeUpdate:
    effective_user: FakeUser | None
    effective_message: FakeMessage | None


@dataclass
class FakeContext:
    args: list[str] = field(default_factory=list)
    error: BaseException | None = None


def make_update(
    user_id: int | None = 111,
    username: str | None = "tester",
    text: str = "/cmd",
) -> FakeUpdate:
    user = FakeUser(id=user_id, username=username) if user_id is not None else None
    return FakeUpdate(effective_user=user, effective_message=FakeMessage(text=text))
