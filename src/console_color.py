"""
TTY-aware ANSI color segments for CLI output and logging.

Uses colorama's ``just_fix_windows_console()`` once at process start so
PowerShell/conhost interpret escapes on both stdout and stderr (Windows).

For partial coloring inside a line (e.g. a status token in a log message),
build the message with :func:`color_segment`::

    msg = f"task {tid} {color_segment(GREEN, 'ok', sys.stdout)} done"
    logger.info(msg)

``NO_COLOR`` disables all escapes. Non-TTY streams return plain text.
"""

from __future__ import annotations

import os
import sys
from typing import TextIO

# SGR sequences (work with just_fix_windows_console on Windows).
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_RED = "\033[91m"
_ORANGE = "\033[38;5;208m"
_DIM = "\033[2m"
_RESET = "\033[0m"

# Public aliases for call sites that prefer short names matching prior cmd_volumes.
GREEN = _GREEN
YELLOW = _YELLOW
RED = _RED
ORANGE = _ORANGE
DIM = _DIM
RESET = _RESET

_win32_console_inited = False


def init_windows_console() -> None:
    """Enable VT processing and UTF-8 on Windows stdout/stderr; no-op elsewhere."""
    global _win32_console_inited
    if _win32_console_inited:
        return
    _win32_console_inited = True
    if sys.platform != "win32":
        return
    try:
        from colorama import just_fix_windows_console

        just_fix_windows_console()
    except Exception:
        pass
    # Reconfigure to UTF-8 so emoji and other non-ASCII characters don't raise
    # UnicodeEncodeError on consoles that default to a narrow encoding (e.g. cp1252).
    # errors="replace" is a safety net; UTF-8 itself can encode all Unicode code points.
    for _stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(_stream, "reconfigure"):
                _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def stream_color_enabled(stream: TextIO) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return bool(hasattr(stream, "isatty") and stream.isatty())


def color_segment(code: str, text: str, stream: TextIO) -> str:
    """Wrap ``text`` with ``code`` and reset when ``stream`` is a color-capable TTY."""
    init_windows_console()
    if not code or not stream_color_enabled(stream):
        return text
    return f"{code}{text}{_RESET}"
