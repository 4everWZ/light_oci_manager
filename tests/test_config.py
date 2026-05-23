from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from app import config
from app.config import ConfigError


def test_loads_valid_config(config_yaml_path: Path) -> None:
    cfg = config.load(config_yaml_path)
    assert cfg.server.port == 8818
    assert cfg.telegram.bot_token == "123:fake-token"
    assert cfg.telegram.allowed_user_ids == frozenset({111, 222})
    assert cfg.oci.default_profile == "p1"
    assert set(cfg.oci.profiles) == {"p1", "p2"}
    assert cfg.oci.profiles["p1"].region == "ap-sydney-1"


def test_get_default_profile(config_yaml_path: Path) -> None:
    cfg = config.load(config_yaml_path)
    assert cfg.oci.get(None).name == "p1"
    assert cfg.oci.get("p2").name == "p2"


def test_get_unknown_profile_raises(config_yaml_path: Path) -> None:
    cfg = config.load(config_yaml_path)
    with pytest.raises(ConfigError, match="Unknown OCI profile 'missing'"):
        cfg.oci.get("missing")


def test_missing_telegram_section(tmp_path: Path, fake_key_file: Path) -> None:
    cfg_path = tmp_path / "config.yml"
    cfg_path.write_text(
        textwrap.dedent(
            f"""\
            oci:
              default_profile: "p1"
              profiles:
                p1:
                  tenancy: "ocid1.t"
                  user: "ocid1.u"
                  fingerprint: "aa"
                  region: "r"
                  key_file: "{fake_key_file}"
                  compartment_id: "ocid1.c"
            """
        )
    )
    with pytest.raises(ConfigError, match="telegram"):
        config.load(cfg_path)


def test_default_profile_not_in_profiles(
    tmp_path: Path, fake_key_file: Path
) -> None:
    cfg_path = tmp_path / "config.yml"
    cfg_path.write_text(
        textwrap.dedent(
            f"""\
            telegram:
              bot_token: "t"
              allowed_user_ids: [1]
            oci:
              default_profile: "missing"
              profiles:
                p1:
                  tenancy: "ocid1.t"
                  user: "ocid1.u"
                  fingerprint: "aa"
                  region: "r"
                  key_file: "{fake_key_file}"
                  compartment_id: "ocid1.c"
            """
        )
    )
    with pytest.raises(ConfigError, match="default_profile"):
        config.load(cfg_path)


def test_keyfile_world_readable_rejected(
    tmp_path: Path, fake_key_file: Path
) -> None:
    os.chmod(fake_key_file, 0o644)
    cfg_path = tmp_path / "config.yml"
    cfg_path.write_text(
        textwrap.dedent(
            f"""\
            telegram:
              bot_token: "t"
              allowed_user_ids: [1]
            oci:
              default_profile: "p1"
              profiles:
                p1:
                  tenancy: "ocid1.t"
                  user: "ocid1.u"
                  fingerprint: "aa"
                  region: "r"
                  key_file: "{fake_key_file}"
                  compartment_id: "ocid1.c"
            """
        )
    )
    with pytest.raises(ConfigError, match="permissive mode"):
        config.load(cfg_path)


def test_missing_keyfile(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.yml"
    cfg_path.write_text(
        textwrap.dedent(
            """\
            telegram:
              bot_token: "t"
              allowed_user_ids: [1]
            oci:
              default_profile: "p1"
              profiles:
                p1:
                  tenancy: "ocid1.t"
                  user: "ocid1.u"
                  fingerprint: "aa"
                  region: "r"
                  key_file: "/nonexistent/key.pem"
                  compartment_id: "ocid1.c"
            """
        )
    )
    with pytest.raises(ConfigError, match="does not exist"):
        config.load(cfg_path)


def test_allowed_user_ids_must_be_ints(
    tmp_path: Path, fake_key_file: Path
) -> None:
    cfg_path = tmp_path / "config.yml"
    cfg_path.write_text(
        textwrap.dedent(
            f"""\
            telegram:
              bot_token: "t"
              allowed_user_ids: ["111"]
            oci:
              default_profile: "p1"
              profiles:
                p1:
                  tenancy: "ocid1.t"
                  user: "ocid1.u"
                  fingerprint: "aa"
                  region: "r"
                  key_file: "{fake_key_file}"
                  compartment_id: "ocid1.c"
            """
        )
    )
    with pytest.raises(ConfigError, match="allowed_user_ids"):
        config.load(cfg_path)
