"""Filenames and save-location helpers."""
from __future__ import annotations

import gc
import os
import re
import sys
from datetime import datetime
from urllib.parse import urlparse


def release_memory() -> None:
    """Return freed heap to the OS after a capture. Large screenshot arrays are
    freed by Python, but the CRT/allocator keeps the pages committed, so a
    long-running app's memory would grow every capture. _heapmin coalesces and
    returns free CRT blocks; SetProcessWorkingSetSize trims the working set."""
    gc.collect()
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.CDLL("msvcrt")._heapmin()
    except Exception:
        pass
    try:
        k = ctypes.windll.kernel32
        k.SetProcessWorkingSetSize(k.GetCurrentProcess(),
                                   ctypes.c_size_t(-1), ctypes.c_size_t(-1))
    except Exception:
        pass


def domain_slug(url: str) -> str:
    try:
        host = urlparse(url).hostname or "page"
    except Exception:
        host = "page"
    host = host.replace("www.", "")
    slug = re.sub(r"[^a-zA-Z0-9.-]", "-", host)
    return slug or "page"


def output_basename(url: str, when: datetime | None = None) -> str:
    when = when or datetime.now()
    return f"PATTISHOT_{domain_slug(url)}_{when:%Y%m%d_%H%M%S}"


def default_save_dir() -> str:
    override = os.environ.get("PATTI_SHOT_OUT_DIR")
    if override:
        os.makedirs(override, exist_ok=True)
        return override
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    d = os.path.join(downloads, "PATTI SHOT")
    os.makedirs(d, exist_ok=True)
    return d


def desktop_dir() -> str:
    """The user's real Desktop folder (handles OneDrive-redirected desktops via
    the shell API). PATTI_SHOT_DESKTOP_DIR overrides for tests."""
    override = os.environ.get("PATTI_SHOT_DESKTOP_DIR")
    if override:
        os.makedirs(override, exist_ok=True)
        return override
    import subprocess
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "[Environment]::GetFolderPath('Desktop')"],
            capture_output=True, text=True, timeout=20,
            creationflags=subprocess.CREATE_NO_WINDOW)
        d = (r.stdout or "").strip()
        if d and os.path.isdir(d):
            return d
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Desktop")


def create_desktop_shortcut(target: str) -> str:
    """Create (or refresh) a 'PATTI SHOT.lnk' on the Desktop pointing at
    ``target``. Returns the .lnk path; raises on failure. The exe carries its
    own embedded icon, so the shortcut gets the PATTI SHOT icon automatically."""
    import subprocess
    lnk = os.path.join(desktop_dir(), "PATTI SHOT.lnk")

    def q(s: str) -> str:  # single-quote for PowerShell (' -> '')
        return "'" + s.replace("'", "''") + "'"

    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut(" + q(lnk) + "); "
          "$s.TargetPath=" + q(target) + "; "
          "$s.WorkingDirectory=" + q(os.path.dirname(target) or ".") + "; "
          "$s.Description='PATTI SHOT - Webページを丸ごと1枚に撮る'; "
          "$s.Save()")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, text=True, timeout=30,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    if r.returncode != 0 or not os.path.exists(lnk):
        raise RuntimeError((r.stderr or r.stdout or "shortcut creation failed").strip()[:200])
    return lnk
