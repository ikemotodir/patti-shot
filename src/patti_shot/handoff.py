"""Open-this-page handoff from the user's normal browser.

Chrome forbids DevTools access to the default profile (136+) and refuses to let
anything attach to an already-running normal Chrome, so PATTI SHOT cannot
capture the window the user already has open. What it CAN do is make "open the
page I'm looking at, here" a single action:

  * a URL on the command line (also accepts ``pattishot://<url>``)
  * the clipboard (Ctrl+L, Ctrl+C in the normal browser, then open PATTI SHOT)
  * the ``pattishot:`` protocol + a bookmarklet -> one click, no copy-paste

A single-instance guard keeps a second launch from opening a second window: the
URL is dropped in a handoff file that the already-running app picks up and opens
as a new tab.
"""
from __future__ import annotations

import ctypes
import os
import re
import subprocess
import sys
import tempfile
from typing import Optional
from urllib.parse import unquote, urlparse

from . import browser

MUTEX_NAME = "Global\\PATTI_SHOT_SINGLE_INSTANCE"
# a hostname label: ascii letters/digits/hyphen, or an IDN (unicode) label
_LABEL_RE = re.compile(r"^[^\s.:/\\?#@]+$")
# the final label must be an ascii TLD, so notes like "ver.4.2.1をリリースした"
# are not mistaken for a host
_TLD_RE = re.compile(r"^[a-z]{2,63}$", re.I)
_IPV4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
_mutex_handle = None  # kept alive for the process lifetime


def _state_dir() -> str:
    d = os.path.dirname(browser.default_profile_dir())  # ...\PATTI SHOT
    os.makedirs(d, exist_ok=True)
    return d


def handoff_path() -> str:
    return os.path.join(_state_dir(), "open_url.txt")


def normalize(raw: Optional[str]) -> Optional[str]:
    """Return a real http(s) URL, or None.

    Deliberately strict: this also vets whatever happens to be in the clipboard,
    so ordinary text must never be coerced into a URL. Coercing e.g. a copied
    bookmarklet ("javascript:...") or a note ("ver.4.2.1をリリースした") produced
    an unreachable address and left the app sitting on a blank page.
    """
    if not raw:
        return None
    s = raw.strip().strip('"\'')
    if not s:
        return None
    s = s.splitlines()[0].strip()
    for prefix in ("pattishot://", "pattishot:"):
        if s.lower().startswith(prefix):
            s = unquote(s[len(prefix):]).strip().strip("/")
            break
    if any(c.isspace() for c in s) or any(c in s for c in "'\"<>{}|^`"):
        return None

    head = s.split("/", 1)[0]
    if ":" in head:                                  # some scheme is present
        if not s.lower().startswith(("http://", "https://")):
            return None                              # javascript:, file:, data: ...
    else:
        s = "https://" + s

    try:
        u = urlparse(s)
    except Exception:
        return None
    if u.scheme not in ("http", "https") or not u.hostname:
        return None

    host = u.hostname
    if host == "localhost" or _IPV4_RE.match(host):
        return u.geturl()
    labels = host.rstrip(".").split(".")
    if len(labels) < 2 or not all(labels):
        return None
    if not _TLD_RE.match(labels[-1]):                # last label must be a real TLD
        return None
    if not all(_LABEL_RE.match(l) for l in labels[:-1]):
        return None
    return u.geturl()


def url_from_argv(argv=None) -> Optional[str]:
    argv = sys.argv[1:] if argv is None else argv
    for a in argv:
        u = normalize(a)
        if u:
            return u
    return None


def url_from_clipboard() -> Optional[str]:
    """A URL sitting in the clipboard (the Ctrl+L, Ctrl+C handoff)."""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                           capture_output=True, text=True, timeout=15,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        return normalize((r.stdout or "").strip().splitlines()[0] if r.stdout.strip() else None)
    except Exception:
        return None


def startup_url() -> Optional[str]:
    """URL this launch should open: command line first, then the clipboard."""
    return url_from_argv() or url_from_clipboard()


# --------------------------------------------------------------------------- #
# single instance
# --------------------------------------------------------------------------- #
def claim_single_instance() -> bool:
    """True when this process is the first PATTI SHOT; False when one is already
    running (the caller should hand its URL over and exit)."""
    global _mutex_handle
    try:
        k = ctypes.windll.kernel32
        h = k.CreateMutexW(None, False, MUTEX_NAME)
        if not h:
            return True  # cannot tell -> behave as the only instance
        if k.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            k.CloseHandle(h)
            return False
        _mutex_handle = h
        return True
    except Exception:
        return True


def send_to_running(url: str) -> bool:
    """Leave a URL for the running instance to open. True when written."""
    try:
        with open(handoff_path(), "w", encoding="utf-8") as f:
            f.write(url)
        return True
    except Exception:
        return False


def take_handoff() -> Optional[str]:
    """Consume a URL left by another launch (called from the app's poll loop)."""
    p = handoff_path()
    try:
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8") as f:
            url = f.read().strip()
        os.remove(p)
        return normalize(url)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# one-click setup: pattishot: protocol + bookmarklet
# --------------------------------------------------------------------------- #
BOOKMARKLET = ("javascript:location.href='pattishot://'+encodeURIComponent(location.href)")


def register_protocol(exe: str) -> None:
    """Register the ``pattishot:`` URL scheme for the current user (no admin).
    Clicking the bookmarklet in any browser then opens the page here."""
    import winreg
    base = r"Software\Classes\pattishot"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, "URL:PATTI SHOT Protocol")
        winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\DefaultIcon") as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, f'"{exe}",0')
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\shell\open\command") as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, f'"{exe}" "%1"')


def set_clipboard(text: str) -> bool:
    try:
        fd, p = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        ps = ("Set-Clipboard -Value (Get-Content -Raw -Encoding UTF8 '"
              + p.replace("'", "''") + "')")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=20,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        os.remove(p)
        return True
    except Exception:
        return False
