from __future__ import annotations

import pytest

from app import resource_match
from app.resource_match import AmbiguousResource, ResourceNotFound
from tests.fakes.oci_fake import FakeInstance


def _inst(id_: str, name: str) -> FakeInstance:
    return FakeInstance(id=id_, display_name=name)


def test_exact_ocid_match() -> None:
    items = [
        _inst("ocid1.instance.oc1.iad.aaaainstance0000abcd1234", "vm-a"),
        _inst("ocid1.instance.oc1.iad.aaaainstance0000efgh5678", "vm-b"),
    ]
    result = resource_match.match(
        "ocid1.instance.oc1.iad.aaaainstance0000abcd1234",
        items,
        profile="p1",
        region="r",
    )
    assert result.display_name == "vm-a"


def test_exact_name_match() -> None:
    items = [_inst("ocid1.instance.oc1.iad.id1", "vm-a"), _inst("ocid1.instance.oc1.iad.id2", "vm-b")]
    result = resource_match.match("vm-a", items, profile="p", region="r")
    assert result.id == "ocid1.instance.oc1.iad.id1"


def test_prefix_match_unique() -> None:
    items = [_inst("ocid1.instance.oc1.iad.id1", "instance-foo"), _inst("ocid1.instance.oc1.iad.id2", "other")]
    result = resource_match.match("instance-", items, profile="p", region="r")
    assert result.display_name == "instance-foo"


def test_prefix_match_ambiguous() -> None:
    items = [
        _inst("ocid1.instance.oc1.iad.id1", "instance-foo"),
        _inst("ocid1.instance.oc1.iad.id2", "instance-bar"),
    ]
    with pytest.raises(AmbiguousResource) as exc:
        resource_match.match("instance-", items, profile="p", region="r")
    assert {c.display_name for c in exc.value.candidates} == {"instance-foo", "instance-bar"}


def test_short_id_match() -> None:
    items = [
        _inst("ocid1.instance.oc1.iad.aaaainstance0000abcd1234", "vm-a"),
        _inst("ocid1.instance.oc1.iad.aaaainstance0000efgh5678", "vm-b"),
    ]
    result = resource_match.match("abcd1234", items, profile="p", region="r")
    assert result.display_name == "vm-a"


def test_not_found_raises() -> None:
    items = [_inst("ocid1.instance.oc1.iad.id1", "vm-a")]
    with pytest.raises(ResourceNotFound):
        resource_match.match("nope", items, profile="p1", region="r1")


def test_empty_query_raises() -> None:
    with pytest.raises(ResourceNotFound):
        resource_match.match("   ", [], profile="p", region="r")


def test_exact_name_beats_prefix() -> None:
    items = [
        _inst("ocid1.instance.oc1.iad.id1", "instance"),
        _inst("ocid1.instance.oc1.iad.id2", "instance-bar"),
    ]
    result = resource_match.match("instance", items, profile="p", region="r")
    assert result.id == "ocid1.instance.oc1.iad.id1"
