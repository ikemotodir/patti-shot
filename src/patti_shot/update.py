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
# (%1 = running exe, %2 = downloaded new exe, %3 = log file) so the batch file
# itself stays ASCII even when the exe lives under a non-ASCII path.
# NOTE: the wait uses `ping -n 2` because timeout.exe errors out instantly in a
# detached console-less process ("Input redirection is not supported"), which
# would burn every retry in milliseconds while the old exe is still running.
# The delete also retries: antivirus briefly locks the fresh download.
# Safety (検証指示書 section 4): the old exe is backed up to <exe>.bak before
# the replace; if the replace fails after all retries the backup is restored so
# the user is never left without a working exe.
_UPDATER_BAT = (
    "@echo off\r\n"
    "setlocal\r\n"
    "echo [bat] updater start>>%3\r\n"
    "set /a BRETRY=0\r\n"
    ":backup\r\n"
    "copy /y %1 %1.bak >nul 2>&1\r\n"
    "if errorlevel 1 (\r\n"
    "  set /a BRETRY+=1\r\n"
    "  if %BRETRY% lss 30 (\r\n"
    "    ping -n 2 127.0.0.1 >nul\r\n"
    "    goto backup\r\n"
    "  )\r\n"
    "  echo [bat] backup FAIL - abort, old exe untouched>>%3\r\n"
    "  goto cleanup\r\n"
    ")\r\n"
    "echo [bat] backup ok>>%3\r\n"
    "set MAXR=%4\r\n"
    "if \"%MAXR%\"==\"\" set MAXR=120\r\n"
    "set /a RETRY=0\r\n"
    ":wait\r\n"
    "ping -n 2 127.0.0.1 >nul\r\n"
    "copy /y %2 %1 >nul 2>&1\r\n"
    "if errorlevel 1 (\r\n"
    "  set /a RETRY+=1\r\n"
    "  if %RETRY% lss %MAXR% goto wait\r\n"
    "  echo [bat] replace FAIL after %MAXR% tries - restoring backup>>%3\r\n"
    "  copy /y %1.bak %1 >nul 2>&1\r\n"
    "  if errorlevel 1 (echo [bat] restore FAIL>>%3) else (echo [bat] restore ok>>%3)\r\n"
    "  goto cleanup\r\n"
    ")\r\n"
    "echo [bat] replace ok>>%3\r\n"
    "rem give real-time antivirus time to finish scanning the freshly-written\r\n"
    "rem exe before relaunching it (Avast blocks launch of a just-created file)\r\n"
    "ping -n 8 127.0.0.1 >nul\r\n"
    "start \"\" %1\r\n"
    "echo [bat] relaunch issued>>%3\r\n"
    ":cleanup\r\n"
    "del /f /q %1.bak >nul 2>&1\r\n"
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
    "echo [bat] done>>%3\r\n"
    "(goto) 2>nul & del \"%~f0\"\r\n"
)

PRODUCT_PAGE = "https://ikemotodir.github.io/patti-shot/"
MANUAL_HINT = f"お手数ですが配布ページ（{PRODUCT_PAGE}）から最新版をダウンロードしてください。"


def log_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    d = os.path.join(base, "STUDIO PATTI", "PATTI SHOT")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "update.log")


def _log(msg: str) -> None:
    """Append a timestamped line to update.log (never raises). The boss can
    copy-paste this file when reporting problems."""
    try:
        import datetime
        with open(log_path(), "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except Exception:
        pass


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
            _log(f"check: current={__version__} latest={tag} -> up to date")
            return None
        for a in data.get("assets", []):
            if a.get("name") == ASSET_NAME and a.get("browser_download_url"):
                _log(f"check: current={__version__} latest={tag} -> update available")
                return {"tag": tag, "url": a["browser_download_url"],
                        "size": int(a.get("size", 0))}
        _log(f"check: latest={tag} but no {ASSET_NAME} asset")
        return None
    except Exception as e:
        # silent by spec (通信失敗時は黙って通常起動) -- but leave a log line
        _log(f"check: failed {type(e).__name__}: {e}")
        return None


def target_exe_path() -> Optional[str]:
    """Path of the running frozen exe (None when running from source)."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.environ.get("PATTI_SHOT_FAKE_EXE")  # test hook


def download(url: str, timeout: float = 300.0) -> str:
    """Download the new exe to a temp file; returns its path. The temp file is
    removed on any failure so aborted downloads never accumulate."""
    fd, dest = tempfile.mkstemp(prefix="PATTI_SHOT_new_", suffix=".exe")
    os.close(fd)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PATTI-SHOT-updater"})
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r, \
                open(dest, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        return dest
    except Exception:
        try:
            os.remove(dest)
        except OSError:
            pass
        raise


def spawn_updater(target: str, new_exe: str, max_retry: int = 120) -> None:
    """Write the updater batch and launch it detached. Caller must exit soon so
    the batch's copy succeeds (it retries until the exe is unlocked). max_retry
    is the replace-retry cap (each ~1s); tests pass a small value so the
    fail-then-restore path completes deterministically."""
    fd, bat = tempfile.mkstemp(prefix="patti_shot_update_", suffix=".bat")
    with os.fdopen(fd, "w", encoding="ascii", newline="") as f:
        f.write(_UPDATER_BAT)
    flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    subprocess.Popen(["cmd", "/c", bat, target, new_exe, log_path(), str(int(max_retry))],
                     creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)


def apply_update(info: dict) -> Optional[str]:
    """Download and hand off to the updater. Returns None on success (caller
    must exit so the updater can replace the exe), or a Japanese error message
    when the update could not be applied (the old exe is left untouched)."""
    target = target_exe_path()
    if not target:
        _log("apply: not a frozen exe; skip")
        return "更新はexe版でのみ利用できます。"
    _log(f"apply: start {info.get('tag')} -> {target}")
    try:
        new_exe = download(info["url"])
    except Exception as e:
        _log(f"apply: download FAILED {type(e).__name__}: {e}")
        return f"新しいバージョンのダウンロードに失敗しました。{MANUAL_HINT}"
    try:
        got = os.path.getsize(new_exe)
        if info.get("size") and got != info["size"]:
            _log(f"apply: size mismatch got={got} expect={info['size']}")
            os.remove(new_exe)
            return (f"ダウンロードしたファイルのサイズが一致しません"
                    f"（{got}≠{info['size']}）。{MANUAL_HINT}")
        _log(f"apply: downloaded ok {got} bytes -> spawning updater")
        spawn_updater(target, new_exe)
        _log("apply: updater spawned; exiting for replace")
        return None
    except Exception as e:
        _log(f"apply: FAILED {type(e).__name__}: {e}")
        try:
            os.remove(new_exe)
        except Exception:
            pass
        return f"更新の適用に失敗しました（{type(e).__name__}）。{MANUAL_HINT}"
