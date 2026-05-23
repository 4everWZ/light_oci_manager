from __future__ import annotations

from telegram.ext import CommandHandler

from app.commands import network
from tests.fakes.oci_fake import FakeIngressRule, FakePortOptions, FakePortRange
from tests.fakes.telegram_fake import FakeContext, make_update


async def _invoke(ctx, cmd_name, args=None):
    handlers = network.make_handlers(ctx)
    cmd_handlers = [h for h in handlers if isinstance(h, CommandHandler)]
    handler = next(h for h in cmd_handlers if cmd_name in h.commands)
    update = make_update()
    await handler.callback(update, FakeContext(args=args or []))
    return update


def test_format_ingress_rule_tcp_single_port() -> None:
    rule = FakeIngressRule(
        protocol="6",
        source="0.0.0.0/0",
        tcp_options=FakePortOptions(destination_port_range=FakePortRange(22, 22)),
    )
    assert network.format_ingress_rule(rule) == "TCP 22 from 0.0.0.0/0"


def test_format_ingress_rule_tcp_port_range() -> None:
    rule = FakeIngressRule(
        protocol="6",
        source="1.2.3.0/24",
        tcp_options=FakePortOptions(destination_port_range=FakePortRange(80, 443)),
    )
    assert network.format_ingress_rule(rule) == "TCP 80-443 from 1.2.3.0/24"


def test_format_ingress_rule_tcp_all_ports() -> None:
    rule = FakeIngressRule(
        protocol="6", source="10.0.0.0/8", tcp_options=FakePortOptions()
    )
    assert network.format_ingress_rule(rule) == "TCP all from 10.0.0.0/8"


def test_format_ingress_rule_udp() -> None:
    rule = FakeIngressRule(
        protocol="17",
        source="10.0.0.0/16",
        udp_options=FakePortOptions(destination_port_range=FakePortRange(53, 53)),
    )
    assert network.format_ingress_rule(rule) == "UDP 53 from 10.0.0.0/16"


def test_format_ingress_rule_icmp() -> None:
    rule = FakeIngressRule(protocol="1", source="0.0.0.0/0")
    assert network.format_ingress_rule(rule) == "ICMP from 0.0.0.0/0"


async def test_security_lists_default_profile(app_ctx) -> None:
    update = await _invoke(app_ctx, "security_lists")
    body = "\n".join(update.effective_message.replies)
    assert "Profile: p1" in body
    assert "Region: ap-sydney-1" in body
    assert "Default Security List" in body
    assert "private-sl" in body
    # Full OCIDs masked.
    assert "ocid1.securitylist.oc1.iad.fakedefaultsl12345abcd" not in body
    assert "ocid1.securitylist..." in body


async def test_security_lists_explicit_empty_profile(app_ctx) -> None:
    update = await _invoke(app_ctx, "security_lists", args=["p2"])
    body = "\n".join(update.effective_message.replies)
    assert "No security lists" in body


async def test_security_lists_unknown_profile(app_ctx) -> None:
    update = await _invoke(app_ctx, "security_lists", args=["missing"])
    assert "Unknown OCI profile" in update.effective_message.replies[-1]


async def test_security_list_by_name_shows_rules(app_ctx) -> None:
    update = await _invoke(
        app_ctx, "security_list", args=["Default Security List"]
    )
    body = "\n".join(update.effective_message.replies)
    assert "Security list: Default Security List" in body
    assert "TCP 22 from 0.0.0.0/0" in body
    assert "TCP 80 from 0.0.0.0/0" in body
    assert "TCP 443 from 0.0.0.0/0" in body
    assert "TCP 8088 from 10.0.0.0/8" in body
    assert "ICMP from 0.0.0.0/0" in body


async def test_security_list_by_short_id(app_ctx) -> None:
    update = await _invoke(app_ctx, "security_list", args=["12345abcd"])
    body = "\n".join(update.effective_message.replies)
    assert "Default Security List" in body


async def test_security_list_not_found(app_ctx) -> None:
    update = await _invoke(app_ctx, "security_list", args=["nope"])
    assert "Resource not found" in update.effective_message.replies[-1]


async def test_security_list_missing_arg(app_ctx) -> None:
    update = await _invoke(app_ctx, "security_list", args=[])
    assert "Usage" in update.effective_message.replies[-1]
