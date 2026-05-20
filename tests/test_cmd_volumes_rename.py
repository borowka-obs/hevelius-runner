from argparse import Namespace
import logging
import os

import cmd_volumes
import pytest


class _DummyConfigManager:
    loaded = True

    def get_paths_config(self):
        return {}


def _rename_args(**overrides):
    args = Namespace(
        old_string="Caldwell 75",
        new_string="RCW 38",
        file=None,
        list=None,
        dir=None,
        all_files=False,
    )
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


def test_rename_basename_literal_with_spaces_and_parens():
    old = "Caldwell 75"
    new = "RCW 38"
    base = "2026-04-18_22-59-27_Caldwell 75_L_180.00s_LIGHT_0004.fits"
    assert cmd_volumes._rename_basename(base, old, new) == (
        "2026-04-18_22-59-27_RCW 38_L_180.00s_LIGHT_0004.fits"
    )

    paren_base = "2026-04-18_M42 (neb)_L_120.00s_LIGHT_0001.fits"
    assert cmd_volumes._rename_basename(paren_base, "M42 (neb)", "NGC 1976") == (
        "2026-04-18_NGC 1976_L_120.00s_LIGHT_0001.fits"
    )


def test_rename_basename_returns_none_when_no_match():
    assert cmd_volumes._rename_basename("plain.fits", "missing", "x") is None


def test_rename_single_file(tmp_path, caplog):
    cm = _DummyConfigManager()
    src = tmp_path / "2026-04-18_22-59-27_Caldwell 75_L_180.00s_LIGHT_0004.fits"
    src.write_bytes(b"fits")
    dst = tmp_path / "2026-04-18_22-59-27_RCW 38_L_180.00s_LIGHT_0004.fits"

    with caplog.at_level(logging.INFO):
        ret = cmd_volumes.rename_files(cm, _rename_args(file=str(src)))
    assert ret == 0
    assert not src.exists()
    assert dst.is_file()
    assert "Caldwell 75" in caplog.text
    assert "RCW 38" in caplog.text
    assert "1 renamed" in caplog.text


def test_rename_dir_skips_unchanged_and_renames_matches(tmp_path, caplog):
    cm = _DummyConfigManager()
    match = tmp_path / "night_Caldwell 75_001.fits"
    other = tmp_path / "night_M42_002.fits"
    match.write_bytes(b"a")
    other.write_bytes(b"b")

    with caplog.at_level(logging.INFO):
        ret = cmd_volumes.rename_files(cm, _rename_args(dir=str(tmp_path)))
    assert ret == 0
    assert not match.exists()
    assert (tmp_path / "night_RCW 38_001.fits").is_file()
    assert other.is_file()
    assert "1 renamed" in caplog.text
    assert "1 unchanged" in caplog.text


def test_rename_cli_parses_subcommand(runner_mod):
    args = runner_mod.build_parser().parse_args(
        ["volumes", "rename", "Caldwell 75", "RCW 38", "-a"]
    )
    assert args.command == "volumes"
    assert args.volumes_cmd == "rename"
    assert args.old_string == "Caldwell 75"
    assert args.new_string == "RCW 38"
    assert args.all_files is True


def test_rename_fails_when_target_exists(tmp_path, caplog):
    cm = _DummyConfigManager()
    src = tmp_path / "frame_Caldwell 75.fits"
    dst = tmp_path / "frame_RCW 38.fits"
    src.write_bytes(b"a")
    dst.write_bytes(b"b")

    with caplog.at_level(logging.INFO):
        ret = cmd_volumes.rename_files(cm, _rename_args(file=str(src)))
    assert ret == 1
    assert src.is_file()
    assert "failed" in caplog.text.lower()
