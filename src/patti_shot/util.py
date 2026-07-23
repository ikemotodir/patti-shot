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
