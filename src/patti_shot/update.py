"""Auto-update via GitHub Releases (spec section 5).

Startup: check the latest release tag; if newer, the injected UI shows an
update button. Applying: download the new exe, write a tiny ASCII/CRLF updater
batch that waits for this process to exit, replaces the exe, and relaunches.
Any network failure is silent -- the app must never fail to start because the
update check failed.
"""
from __future__ import annotations

import json
import os
import ssl
import subprocess
import sys
import tempfile
import urllib.request
from typing import Optional, Tuple


def _ssl_context() -> ssl.SSLContext:
    """Default verification minus VERIFY_X509_STRICT. Python 3.13+ turns strict
    mode on, which rejects the interception CAs some security software installs
    ("Basic Constraints of CA cert not marked critical") -- the chain is still
    fully verified against the trust store, just without the strict extras."""
    ctx = ssl.create_default_context()
    try:
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    except Exception:
        pass
    return ctx

from . import __version__

REPO = "ikemotodir/patti-shot"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET_NAME = "PATTI_SHOT.exe"

# ASCII only / CRLF / no chcp (spec section 0). Paths are passed as arguments
# (%1 = running exe, %2 = downloaded new exe) so the batch file itself stays
# ASCII even when the exe lives under a non-ASCII path.
# NOTE: the wait uses `ping -n 2` because timeout.exe errors out instantly in a
# detached console-less process ("Input redirection is not supported"), which
# would burn every retry in milliseconds while the old exe is still running.
# The delete also retries: antivirus briefly locks the fresh download.
_UPDATER_BAT = (
    "@echo off\r\n"
    "setlocal\r\n"
    "set /a RETRY=0\r\n"
    ":wait\r\n"
    "ping -n 2 127.0.0.1 >nul\r\n"
    "copy /y %2 %1 >nul 2>&1\r\n"
    "if errorlevel 1 (\r\n"
    "  set /a RETRY+=1\r\n"
    "  if %RETRY% lss 120 goto wait\r\n"
    "  goto cleanup\r\n"
    ")\r\n"
    "start \"\" %1\r\n"
    ":cleanup\r\n"
    "set /a DRETRY=0\r\n"
    ":delloop\r\n"
    "del /f /q %2 >nul 2>&1\r\n"
    "if exist %2 (\r\n"
    "  set /a DRETRY+=1\r\n"
    "  if %DRETRY% lss 30 (\r\n"
    "    ping -n 2 127.0.0.1 >nul\r\n"
    "    goto delloop\r\n"
    "  )\r\n"
    ")\r\n"
    "(goto) 2>nul & del \"%~f0\"\r\n"
)


def _parse_ver(s: str) -> Tuple[int, ...]:
    s = s.strip().lstrip("vV")
    parts = []
    for tok in s.split("."):
        num = "".join(ch for ch in tok if ch.isdigit())
        parts.append(int(num) if num else 0)
    return tuple(parts) or (0,)


def check_latest(timeout: float = 6.0) -> Optional[dict]:
    """Return {tag, url, size} when a newer release exists, else None.
    Silent on ANY failure (spec: 通信失敗時は黙って通常起動)."""
    api = os.environ.get("PATTI_SHOT_UPDATE_API", API_LATEST)
    try:
        req = urllib.request.Request(api, headers={
            "User-Agent": "PATTI-SHOT-updater",
            "Accept": "application/vnd.github+json",
        })
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r:
            data = json.load(r)
        tag = data.get("tag_name") or ""
        if _parse_ver(tag) <= _parse_ver(__version__):
            return None
        for a in data.get("assets", []):
            if a.get("name") == ASSET_NAME and a.get("browser_download_url"):
                return {"tag": tag, "url": a["browser_download_url"],
                        "size": int(a.get("size", 0))}
        return None
    except Exception:
        return None


def target_exe_path() -> Optional[str]:
    """Path of the running frozen exe (None when running from source)."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.environ.get("PATTI_SHOT_FAKE_EXE")  # test hook


def download(url: str, timeout: float = 300.0) -> str:
    """Download the new exe to a temp file; returns its path."""
    fd, dest = tempfile.mkstemp(prefix="PATTI_SHOT_new_", suffix=".exe")
    os.close(fd)
    req = urllib.request.Request(url, headers={"User-Agent": "PATTI-SHOT-updater"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r, \
            open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    return dest


def spawn_updater(target: str, new_exe: str) -> None:
    """Write the updater batch and launch it detached. Caller must exit soon so
    the batch's copy succeeds (it retries until the exe is unlocked)."""
    fd, bat = tempfile.mkstemp(prefix="patti_shot_update_", suffix=".bat")
    with os.fdopen(fd, "w", encoding="ascii", newline="") as f:
        f.write(_UPDATER_BAT)
    flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    subprocess.Popen(["cmd", "/c", bat, target, new_exe],
                     creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)


def apply_update(info: dict) -> bool:
    """Download and hand off to the updater. Returns True when the caller
    should exit (updater spawned)."""
    target = target_exe_path()
    if not target:
        return False
    try:
        new_exe = download(info["url"])
        if info.get("size") and os.path.getsize(new_exe) != info["size"]:
            os.remove(new_exe)
            return False
        spawn_updater(target, new_exe)
        return True
    except Exception:
        return False
