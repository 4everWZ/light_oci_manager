"""JSON-lines audit log.

Spec §8.4: every command writes a record with timestamp, telegram_user_id,
username, command, profile, target_resource, result, error_message.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class AuditLogger:
    """Append-only JSONL writer with an asyncio lock to keep lines atomic.

    The lock matters because Telegram updates are concurrent and each command
    handler emits exactly one audit record. Without the lock two interleaved
    writes could produce a broken JSON line.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = Path(path)
        self._lock = asyncio.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    async def record(
        self,
        *,
        user_id: int | None,
        username: str | None,
        command: str,
        profile: str | None = None,
        target: str | None = None,
        result: str = "ok",
        error: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        record: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "user_id": user_id,
            "username": username,
            "cmd": command,
            "result": result,
        }
        if profile is not None:
            record["profile"] = profile
        if target is not None:
            record["target"] = target
        if error is not None:
            record["error"] = error
        if extra:
            record.update(extra)

        line = json.dumps(record, ensure_ascii=False, sort_keys=False) + "\n"
        async with self._lock:
            # Synchronous write inside the lock is fine — it is a single short
            # line and the alternative (aiofiles) adds a dependency for no
            # measurable benefit at this volume.
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line)
