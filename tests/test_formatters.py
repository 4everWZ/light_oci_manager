from __future__ import annotations

from app.formatters import (
    IpRow,
    chunk_message,
    format_instance_summary,
    format_instances_page,
    format_ip_row,
    paginate,
)
from tests.fakes.oci_fake import FakeInstance, FakeShapeConfig


def test_format_instance_summary_includes_basics() -> None:
    inst = FakeInstance(
        id="ocid1.instance.oc1.iad.aaaainstance0000abcd1234",
        display_name="vm-a",
        shape_config=FakeShapeConfig(ocpus=2.0, memory_in_gbs=12.0),
    )
    s = format_instance_summary(1, inst)
    assert "1. vm-a" in s
    assert "RUNNING" in s
    assert "OCPU: 2" in s
    assert "Memory: 12 GB" in s
    # Full OCID must not leak.
    assert inst.id not in s
    assert "ocid1.instance..." in s


def test_format_instances_page_empty() -> None:
    out = format_instances_page("p1", "r1", [])
    assert "No instances" in out
    assert "Profile: p1" in out


def test_format_ip_row_handles_none_public_ip() -> None:
    row = IpRow(
        instance_name="vm",
        instance_id="ocid1.instance.oc1.iad.aaaainstance0000abcd1234",
        public_ip=None,
        private_ip="10.0.0.5",
        subnet_id="ocid1.subnet.oc1.iad.subnet0000abcd",
        vnic_id="ocid1.vnic.oc1.iad.vnic0000abcd",
        state="RUNNING",
    )
    s = format_ip_row(row)
    assert "Public IP: -" in s
    assert "Private IP: 10.0.0.5" in s
    assert "ocid1.subnet..." in s


def test_chunk_message_no_split_when_small() -> None:
    text = "a\nb\nc"
    assert chunk_message(text) == [text]


def test_chunk_message_splits_on_line_boundary() -> None:
    text = "\n".join(f"line-{i:03d}" for i in range(2000))
    chunks = chunk_message(text, limit=200)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 200
    # Reassembly is lossless.
    assert "\n".join(chunks) == text


def test_paginate_splits_into_chunks() -> None:
    items = [
        FakeInstance(id=f"ocid1.instance.oc1.iad.id{i:04d}{'x' * 8}", display_name=f"vm-{i}")
        for i in range(5)
    ]
    pages = list(paginate(items, page_size=2))
    assert [len(p) for p in pages] == [2, 2, 1]


def test_paginate_zero_yields_all() -> None:
    items = [FakeInstance(id="ocid1.instance.oc1.iad.id00000000abcd", display_name="x")]
    pages = list(paginate(items, page_size=0))
    assert pages == [items]
