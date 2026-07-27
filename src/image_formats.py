"""
Generic astronomical image format handling.

Discovers supported image files on disk and reads metadata headers in a
format-agnostic way. Callers should use :func:`read_header` and
:func:`image_files_in_dir` rather than format-specific helpers.

Supported today:
  - FITS (``.fit``, ``.fits``, ``.fts``) via astropy
  - XISF (``.xisf``) via the ``xisf`` package (PixInsight / NINA)

Future candidates (not implemented — see module docstring notes below):
  - Canon CR2 (``.cr2``): metadata is EXIF/MakerNote, not FITS keywords.
    Mapping ``OBJECT`` / ``FILTER`` / ``EXPTIME`` / ``OBJCTRA`` / ``OBJCTDEC``
    from camera EXIF is incomplete for observatory workflows (e.g. filter wheel
    and target name are usually absent). A reasonable path later is
    ``exifread`` (lightweight, pure Python) or ``pyexiftool``, plus an explicit
    alias map and likely filename-based fallbacks. Prefer keeping CR2 out of
    the default extension set until that mapping is validated against real
    NINA/observatory CR2 samples.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Union

from fits import read_fits

# Extensions are stored lowercase, with leading dot.
_FITS_EXTENSIONS = (".fit", ".fits", ".fts")
_XISF_EXTENSIONS = (".xisf",)

# Ordered for stable glob / display; add new formats here.
SUPPORTED_EXTENSIONS: tuple[str, ...] = _FITS_EXTENSIONS + _XISF_EXTENSIONS

Header = MutableMapping[str, Any]
PathLike = Union[str, os.PathLike]


def normalize_extension(path: PathLike) -> str:
    """Return the file extension in lowercase, including the leading dot."""
    return Path(path).suffix.lower()


def is_supported_image(path: PathLike) -> bool:
    """True if ``path`` has a known astronomical image extension."""
    return normalize_extension(path) in SUPPORTED_EXTENSIONS


def supported_extensions_glob_display() -> str:
    """Human-readable extension list, e.g. ``*.fit/*.fits/*.fts/*.xisf``."""
    return "/".join(f"*{ext}" for ext in SUPPORTED_EXTENSIONS)


def image_files_in_dir(dir_path: PathLike) -> List[str]:
    """
    Return sorted absolute paths of supported image files under ``dir_path``.

    Walk is recursive. Matching is case-insensitive on the extension
    (important on case-sensitive filesystems).
    """
    base = Path(os.path.normpath(str(dir_path)))
    if not base.is_dir():
        return []

    found: List[str] = []
    for root, _dirs, files in os.walk(base):
        for name in files:
            if is_supported_image(name):
                found.append(str(Path(root) / name))
    return sorted(found)


def read_header(filename: PathLike) -> Header:
    """
    Read image metadata as a dict-like mapping of FITS-style keyword → value.

    Dispatches by file extension. Raises ``ValueError`` for unsupported types
    and propagates I/O / parser errors from the underlying library.
    """
    path = str(filename)
    ext = normalize_extension(path)

    if ext in _FITS_EXTENSIONS:
        return read_fits(path)
    if ext in _XISF_EXTENSIONS:
        return read_xisf_header(path)

    raise ValueError(
        f"Unsupported image format for {path!r} "
        f"(extension {ext!r}; supported: {', '.join(SUPPORTED_EXTENSIONS)})"
    )


def read_xisf_header(filename: PathLike) -> Dict[str, Any]:
    """
    Read FITS-compatible keywords from an XISF file header.

    Uses the ``xisf`` package (https://pypi.org/project/xisf/). Only the XML
    metadata is needed; pixel data is not loaded.

    XISF stores FITS keywords as lists of ``{value, comment}`` entries (a name
    may appear more than once). This returns a flat dict using the first value
    for each name, which matches how volumes processing uses keys today.
    """
    try:
        from xisf import XISF
    except ImportError as e:
        raise ImportError(
            "Reading XISF files requires the 'xisf' package. "
            "Install it with: pip install xisf"
        ) from e

    path = str(filename)
    xisf = XISF(path)
    images_meta = xisf.get_images_metadata()
    if not images_meta:
        return {}

    fits_keywords = images_meta[0].get("FITSKeywords") or {}
    return _flatten_xisf_fits_keywords(fits_keywords)


def _flatten_xisf_fits_keywords(
    fits_keywords: Mapping[str, Sequence[Mapping[str, Any]]],
) -> Dict[str, Any]:
    """Convert XISF FITSKeywords structure to a flat keyword → value dict."""
    header: Dict[str, Any] = {}
    for name, entries in fits_keywords.items():
        if not entries:
            continue
        first = entries[0]
        if isinstance(first, Mapping) and "value" in first:
            header[str(name)] = first["value"]
        else:
            header[str(name)] = first
    return header


def header_items(header: Mapping[str, Any]) -> Iterable[tuple[str, Any]]:
    """Iterate ``(key, value)`` pairs for display (works for dict and astropy Header)."""
    for key in header.keys():
        yield key, header[key]
