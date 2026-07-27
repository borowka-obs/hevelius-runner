"""Tests for format-agnostic image discovery and header reading."""

from pathlib import Path

import numpy as np
import pytest

import image_formats


def test_supported_extensions_include_fits_and_xisf():
    assert ".fit" in image_formats.SUPPORTED_EXTENSIONS
    assert ".fits" in image_formats.SUPPORTED_EXTENSIONS
    assert ".fts" in image_formats.SUPPORTED_EXTENSIONS
    assert ".xisf" in image_formats.SUPPORTED_EXTENSIONS
    assert ".cr2" not in image_formats.SUPPORTED_EXTENSIONS


def test_is_supported_image_case_insensitive():
    assert image_formats.is_supported_image("frame.FITS")
    assert image_formats.is_supported_image("frame.Xisf")
    assert image_formats.is_supported_image("frame.fts")
    assert not image_formats.is_supported_image("frame.cr2")
    assert not image_formats.is_supported_image("notes.txt")


def test_image_files_in_dir_finds_fits_and_xisf(tmp_path: Path):
    (tmp_path / "a.fits").write_bytes(b"")
    (tmp_path / "b.fit").write_bytes(b"")
    (tmp_path / "c.xisf").write_bytes(b"")
    (tmp_path / "d.CR2").write_bytes(b"")
    nested = tmp_path / "night"
    nested.mkdir()
    (nested / "e.FTS").write_bytes(b"")
    (nested / "ignore.txt").write_bytes(b"")

    found = image_formats.image_files_in_dir(tmp_path)
    basenames = sorted(Path(p).name.lower() for p in found)
    assert basenames == ["a.fits", "b.fit", "c.xisf", "e.fts"]


def test_flatten_xisf_fits_keywords_takes_first_value():
    flat = image_formats._flatten_xisf_fits_keywords(
        {
            "OBJECT": [{"value": "M42", "comment": "first"}, {"value": "other", "comment": ""}],
            "FILTER": [{"value": "Ha", "comment": ""}],
            "EMPTY": [],
        }
    )
    assert flat == {"OBJECT": "M42", "FILTER": "Ha"}


def test_read_header_rejects_unsupported_extension(tmp_path: Path):
    path = tmp_path / "photo.cr2"
    path.write_bytes(b"")
    with pytest.raises(ValueError, match="Unsupported image format"):
        image_formats.read_header(path)


def test_read_xisf_header_roundtrip(tmp_path: Path):
    pytest.importorskip("xisf")
    from xisf import XISF

    path = tmp_path / "sample.xisf"
    img = np.zeros((8, 8, 1), dtype=np.float32)
    meta = {
        "FITSKeywords": {
            "OBJECT": [{"value": "M42", "comment": "target"}],
            "FILTER": [{"value": "Ha", "comment": ""}],
            "EXPTIME": [{"value": "300.0", "comment": "s"}],
            "XBINNING": [{"value": "2", "comment": ""}],
        }
    }
    XISF.write(str(path), img, image_metadata=meta)

    header = image_formats.read_header(path)
    assert header["OBJECT"] == "M42"
    assert header["FILTER"] == "Ha"
    assert header["EXPTIME"] == "300.0"
    assert header["XBINNING"] == "2"


def test_cmd_volumes_image_files_in_dir_uses_shared_discovery(tmp_path: Path, monkeypatch):
    import cmd_volumes

    (tmp_path / "one.fits").write_bytes(b"")
    (tmp_path / "two.xisf").write_bytes(b"")
    paths = cmd_volumes._image_files_in_dir(str(tmp_path))
    names = sorted(Path(p).name for p in paths)
    assert names == ["one.fits", "two.xisf"]
