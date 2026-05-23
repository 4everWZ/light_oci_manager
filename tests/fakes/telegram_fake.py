"""Test doubles for telegram Update/Context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeUser:
    id: int
    username: str | None = None


class FakeMessage:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.replies: list[str] = []
        self.reply_markups: list[Any] = []

    async def reply_text(self, text: str, reply_markup: Any | None = None) -> None:
        self.replies.append(text)
        self.reply_markups.append(reply_markup)


class FakeCallbackQuery:
    def __init__(
        self,
        data: str,
        user_id: int | None = 111,
        username: str | None = "tester",
    ) -> None:
        self.data = data
        self.from_user = (
            FakeUser(id=user_id, username=username) if user_id is not None else None
        )
        self.answered = False
        self.edited_text: str | None = None

    async def answer(self, *_args, **_kwargs) -> None:
        self.answered = True

    async def edit_message_text(self, text: str, *_args, **_kwargs) -> None:
        self.edited_text = text


@dataclass
class FakeUpdate:
    effective_user: FakeUser | None
    effective_message: FakeMessage | None
    callback_query: FakeCallbackQuery | None = None


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


def make_callback_update(
    data: str,
    user_id: int | None = 111,
    username: str | None = "tester",
) -> FakeUpdate:
    user = FakeUser(id=user_id, username=username) if user_id is not None else None
    query = FakeCallbackQuery(data=data, user_id=user_id, username=username)
    return FakeUpdate(effective_user=user, effective_message=None, callback_query=query)
