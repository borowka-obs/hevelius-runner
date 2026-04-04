import textwrap

import pytest

from config_manager import ConfigManager


def test_missing_config_file_does_not_raise(tmp_path):
    missing = tmp_path / "missing.yaml"
    cm = ConfigManager(str(missing))
    assert cm.loaded is False
    assert cm.raw is None
    assert cm.get_api_config() == {}


def test_loads_valid_yaml(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(
        textwrap.dedent(
            """
            api:
              base_url: https://example.test/api/
              timeout: 42
              username: u
              password: secret
              verify_ssl: false
            paths:
              template_dir: t
              output_dir: o
            """
        ).strip(),
        encoding="utf-8",
    )
    cm = ConfigManager(str(p))
    assert cm.loaded is True
    api = cm.get_api_config()
    assert api["base_url"] == "https://example.test/api/"
    assert api["timeout"] == 42
    assert api["verify_ssl"] is False


def test_redacted_copy_masks_password(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(
        "api:\n  password: supersecret\n  base_url: http://x\n",
        encoding="utf-8",
    )
    cm = ConfigManager(str(p))
    red = cm.redacted_copy()
    assert red["api"]["password"] == "***"


def test_invalid_yaml_does_not_raise(tmp_path, capsys):
    p = tmp_path / "bad.yaml"
    p.write_text("api: [\n", encoding="utf-8")
    cm = ConfigManager(str(p))
    assert cm.loaded is False
    err = capsys.readouterr().err.lower()
    assert "yaml" in err or "parse" in err
