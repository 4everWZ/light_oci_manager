"""Telegram-friendly formatters.

Telegram's hard message cap is 4096 characters. ``chunk_message`` splits long
strings on line boundaries so the bot can send a list of messages without
breaking lines mid-record.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from app.security import mask_ocid

TELEGRAM_MESSAGE_LIMIT = 4000  # below the hard cap to leave headroom


class InstanceLike(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def display_name(self) -> str: ...

    @property
    def lifecycle_state(self) -> str: ...

    @property
    def shape(self) -> str: ...

    @property
    def availability_domain(self) -> str: ...

    @property
    def shape_config(self) -> ShapeConfigLike | None: ...


class ShapeConfigLike(Protocol):
    @property
    def ocpus(self) -> float | int | None: ...

    @property
    def memory_in_gbs(self) -> float | int | None: ...


@dataclass(frozen=True)
class IpRow:
    instance_name: str
    instance_id: str
    public_ip: str | None
    private_ip: str | None
    subnet_id: str | None
    vnic_id: str | None
    state: str


def format_instance_summary(idx: int, inst: InstanceLike) -> str:
    cfg = inst.shape_config
    ocpu = getattr(cfg, "ocpus", None) if cfg else None
    mem = getattr(cfg, "memory_in_gbs", None) if cfg else None
    lines = [
        f"{idx}. {inst.display_name}",
        f"   State: {inst.lifecycle_state}",
        f"   Shape: {inst.shape}",
    ]
    if ocpu is not None:
        lines.append(f"   OCPU: {_fmt_num(ocpu)}")
    if mem is not None:
        lines.append(f"   Memory: {_fmt_num(mem)} GB")
    lines.append(f"   AD: {inst.availability_domain}")
    lines.append(f"   ID: {mask_ocid(inst.id)}")
    return "\n".join(lines)


def format_instances_page(
    profile: str,
    region: str,
    instances: list[InstanceLike],
) -> str:
    if not instances:
        return f"Profile: {profile}\nRegion: {region}\n\nNo instances in compartment."
    head = f"Profile: {profile}\nRegion: {region}\n"
    body = "\n\n".join(
        format_instance_summary(i + 1, inst) for i, inst in enumerate(instances)
    )
    return f"{head}\n{body}"


def format_ip_row(row: IpRow) -> str:
    lines = [
        f"Instance: {row.instance_name}",
        f"State: {row.state}",
        f"Public IP: {row.public_ip or '-'}",
        f"Private IP: {row.private_ip or '-'}",
    ]
    if row.subnet_id:
        lines.append(f"Subnet: {mask_ocid(row.subnet_id)}")
    if row.vnic_id:
        lines.append(f"VNIC: {mask_ocid(row.vnic_id)}")
    return "\n".join(lines)


def chunk_message(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Split ``text`` into chunks of at most ``limit`` chars on line boundaries.

    The function never splits a single line. If one line on its own exceeds
    ``limit`` it is emitted as its own oversized chunk; Telegram will reject
    that and the caller will see a clear failure rather than mysteriously
    truncated output.
    """
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for line in text.split("\n"):
        line_len = len(line) + 1  # +1 for the newline we'll re-insert
        if buf_len + line_len > limit and buf:
            chunks.append("\n".join(buf))
            buf = [line]
            buf_len = line_len
        else:
            buf.append(line)
            buf_len += line_len
    if buf:
        chunks.append("\n".join(buf))
    return chunks


def paginate(items: list[InstanceLike], page_size: int) -> Iterable[list[InstanceLike]]:
    if page_size <= 0:
        yield items
        return
    for start in range(0, len(items), page_size):
        yield items[start : start + page_size]


def _fmt_num(value: float | int) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
