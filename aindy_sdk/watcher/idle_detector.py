"""
idle_detector.py — seconds since the user last touched the keyboard or mouse (FR-65).

Contract:
  - seconds_since_input() NEVER raises. It returns a float, or None when this platform's
    source is unavailable; None means "unknown", never "active".
  - Zero dependencies: ctypes on Windows, subprocesses elsewhere.

Platform strategy:
  - Windows: user32.GetLastInputInfo against kernel32.GetTickCount (both 32-bit ms
    counters; the difference is taken modulo 2**32 so it survives the 49.7-day wrap).
  - macOS: `ioreg -c IOHIDSystem`, HIDIdleTime (nanoseconds).
  - Linux: `xprintidle` (milliseconds), when installed. Wayland sessions usually have no
    equivalent, so this answers None there.
"""

from __future__ import annotations

import logging
import platform
import re
import shutil
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

_SYSTEM = platform.system()
_warned = False


def _warn_once(message: str, *args) -> None:
    global _warned
    if not _warned:
        _warned = True
        logger.warning(message, *args)


def _idle_windows() -> Optional[float]:
    import ctypes
    import ctypes.wintypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.wintypes.UINT), ("dwTime", ctypes.wintypes.DWORD)]

    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    now = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
    return ((now - info.dwTime) & 0xFFFFFFFF) / 1000.0


_HID_IDLE = re.compile(r'"HIDIdleTime"\s*=\s*(\d+)')


def _idle_macos() -> Optional[float]:
    out = subprocess.run(
        ["ioreg", "-c", "IOHIDSystem"], capture_output=True, text=True, timeout=2, check=False
    ).stdout
    match = _HID_IDLE.search(out or "")
    return int(match.group(1)) / 1e9 if match else None


def _idle_linux() -> Optional[float]:
    if not shutil.which("xprintidle"):
        _warn_once("Idle detection needs `xprintidle` on Linux; sessions end only on a lock or a stop.")
        return None
    out = subprocess.run(["xprintidle"], capture_output=True, text=True, timeout=2, check=False)
    text = (out.stdout or "").strip()
    return int(text) / 1000.0 if out.returncode == 0 and text.isdigit() else None


def seconds_since_input() -> Optional[float]:
    """Seconds since the last keyboard or mouse input, or None when it can't be read."""
    try:
        if _SYSTEM == "Windows":
            return _idle_windows()
        if _SYSTEM == "Darwin":
            return _idle_macos()
        if _SYSTEM == "Linux":
            return _idle_linux()
    except Exception as exc:  # noqa: BLE001 — never raise into the sampling loop
        _warn_once("Idle detection failed (%s); sessions end only on a lock or a stop.", exc)
    return None
