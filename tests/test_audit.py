from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.audit import AuditLogger


@pytest.mark.asyncio
async def test_record_writes_jsonl(tmp_path: Path) -> None:
    log = AuditLogger(tmp_path / "audit.log")
    await log.record(user_id=1, username="u", command="/instances", result="ok")
    await log.record(
        user_id=2,
        username="v",
        command="/stop_instance",
        profile="p1",
        target="ocid1.instance.x",
        result="error",
        error="not allowed",
    )
    lines = (tmp_path / "audit.log").read_text().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["cmd"] == "/instances"
    assert first["user_id"] == 1
    assert first["result"] == "ok"
    assert "ts" in first
    assert first["ts"].endswith("Z")
    assert second["profile"] == "p1"
    assert second["target"] == "ocid1.instance.x"
    assert second["result"] == "error"
    assert second["error"] == "not allowed"


@pytest.mark.asyncio
async def test_record_concurrent_lines_are_intact(tmp_path: Path) -> None:
    import asyncio

    log = AuditLogger(tmp_path / "audit.log")
    await asyncio.gather(
        *(
            log.record(user_id=i, username=f"u{i}", command="/x", result="ok")
            for i in range(20)
        )
    )
    lines = (tmp_path / "audit.log").read_text().splitlines()
    assert len(lines) == 20
    # All lines must parse as JSON.
    for line in lines:
        json.loads(line)


@pytest.mark.asyncio
async def test_record_creates_parent_dir(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "nested" / "audit.log"
    log = AuditLogger(nested)
    await log.record(user_id=1, username="u", command="/x")
    assert nested.exists()
