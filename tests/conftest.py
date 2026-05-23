"""Shared fixtures."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from app.audit import AuditLogger
from app.config import (
    AppConfig,
    OciProfile,
    OciSection,
    RuntimeConfig,
    ServerConfig,
    TelegramConfig,
)
from app.confirmations import ConfirmationStore
from app.context import AppContext
from tests.fakes.oci_fake import FakeInstance, FakeOciClient, FakeVnic


@pytest.fixture
def fake_key_file(tmp_path: Path) -> Path:
    """A file with 0o600 perms standing in for an OCI API private key."""
    path = tmp_path / "fake_api_key.pem"
    path.write_text("-----BEGIN FAKE KEY-----\n")
    os.chmod(path, 0o600)
    return path


@pytest.fixture
def config_yaml_path(tmp_path: Path, fake_key_file: Path) -> Path:
    cfg = tmp_path / "config.yml"
    cfg.write_text(
        textwrap.dedent(
            f"""\
            server:
              host: "127.0.0.1"
              port: 8818

            telegram:
              bot_token: "123:fake-token"
              allowed_user_ids:
                - 111
                - 222

            oci:
              default_profile: "p1"
              profiles:
                p1:
                  tenancy: "ocid1.tenancy.oc1..fake1"
                  user: "ocid1.user.oc1..fake1"
                  fingerprint: "aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99"
                  region: "ap-sydney-1"
                  key_file: "{fake_key_file}"
                  compartment_id: "ocid1.compartment.oc1..fake1"
                p2:
                  tenancy: "ocid1.tenancy.oc1..fake2"
                  user: "ocid1.user.oc1..fake2"
                  fingerprint: "aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99"
                  region: "us-ashburn-1"
                  key_file: "{fake_key_file}"
                  compartment_id: "ocid1.compartment.oc1..fake2"

            runtime:
              default_page_size: 20
              command_timeout_sec: 30
              confirmation_ttl_sec: 60
              audit_log: "{tmp_path / "audit.log"}"
            """
        )
    )
    return cfg


@pytest.fixture
def app_config(tmp_path: Path, fake_key_file: Path) -> AppConfig:
    """Constructed in-memory to keep config-loader tests separate."""
    profiles = {
        "p1": OciProfile(
            name="p1",
            tenancy="ocid1.tenancy.oc1..fake1",
            user="ocid1.user.oc1..fake1",
            fingerprint="aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99",
            region="ap-sydney-1",
            key_file=str(fake_key_file),
            compartment_id="ocid1.compartment.oc1..fake1",
        ),
        "p2": OciProfile(
            name="p2",
            tenancy="ocid1.tenancy.oc1..fake2",
            user="ocid1.user.oc1..fake2",
            fingerprint="aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99",
            region="us-ashburn-1",
            key_file=str(fake_key_file),
            compartment_id="ocid1.compartment.oc1..fake2",
        ),
    }
    return AppConfig(
        server=ServerConfig(host="127.0.0.1", port=8818),
        telegram=TelegramConfig(
            bot_token="123:fake",
            allowed_user_ids=frozenset({111, 222}),
        ),
        oci=OciSection(default_profile="p1", profiles=profiles),
        runtime=RuntimeConfig(audit_log=str(tmp_path / "audit.log")),
        source_path=tmp_path / "config.yml",
    )


@pytest.fixture
def audit_logger(tmp_path: Path) -> AuditLogger:
    return AuditLogger(tmp_path / "audit.log")


@pytest.fixture
def fake_instances() -> dict[str, list[FakeInstance]]:
    return {
        "p1": [
            FakeInstance(
                id="ocid1.instance.oc1.iad.aaaainstance0000abcd1234",
                display_name="instance-20260331-2201",
            ),
            FakeInstance(
                id="ocid1.instance.oc1.iad.aaaainstance0000efgh5678",
                display_name="instance-20260401-0900",
                lifecycle_state="STOPPED",
            ),
        ],
        "p2": [
            FakeInstance(
                id="ocid1.instance.oc1.phx.aaaainstance0000ijkl9999",
                display_name="ash-vm-01",
            ),
        ],
    }


@pytest.fixture
def fake_vnics() -> dict[str, FakeVnic]:
    return {
        "ocid1.instance.oc1.iad.aaaainstance0000abcd1234": FakeVnic(
            id="ocid1.vnic.oc1.iad.fake-vnic-1",
            public_ip="192.0.2.10",
            private_ip="10.0.0.10",
            subnet_id="ocid1.subnet.oc1.iad.fake-subnet-1",
        ),
        "ocid1.instance.oc1.iad.aaaainstance0000efgh5678": FakeVnic(
            id="ocid1.vnic.oc1.iad.fake-vnic-2",
            public_ip=None,
            private_ip="10.0.0.11",
            subnet_id="ocid1.subnet.oc1.iad.fake-subnet-1",
        ),
    }


@pytest.fixture
def fake_oci(
    fake_instances: dict[str, list[FakeInstance]],
    fake_vnics: dict[str, FakeVnic],
) -> FakeOciClient:
    return FakeOciClient(fake_instances, fake_vnics, default_profile="p1")


@pytest.fixture
def app_ctx(
    app_config: AppConfig,
    audit_logger: AuditLogger,
    fake_oci: FakeOciClient,
) -> AppContext:
    return AppContext(
        config=app_config,
        oci=fake_oci,  # type: ignore[arg-type]  # duck-typed for tests
        audit=audit_logger,
        confirmations=ConfirmationStore(ttl_sec=60),
        version="0.1.0-test",
    )
