"""Browser launch and persistent profile management.

Primary path uses the user's installed Chrome (channel="chrome") with a
persistent profile so logins survive restarts (spec section 3). If Chrome is
absent, falls back to the bundled Chromium once (no user action required).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from playwright.sync_api import BrowserContext, Playwright

from .jslib import BROWSER_JS


def default_profile_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "STUDIO PATTI", "PATTI SHOT", "profile")
    os.makedirs(d, exist_ok=True)
    return d


@dataclass
class LaunchResult:
    context: BrowserContext
    channel: str  # "chrome" or "chromium"


def launch(pw: Playwright, profile_dir: str, headless: bool = False,
           viewport: Optional[dict] = None, prefer_chrome: bool = True) -> LaunchResult:
    common = dict(
        user_data_dir=profile_dir,
        headless=headless,
        viewport=viewport,          # None => use real window size (headed)
        args=["--hide-crash-restore-bubble", "--no-first-run",
              "--no-default-browser-check"],
        ignore_default_args=["--enable-automation"],
    )
    last_err = None
    if prefer_chrome:
        try:
            ctx = pw.chromium.launch_persistent_context(channel="chrome", **common)
            ctx.add_init_script(BROWSER_JS)
            return LaunchResult(ctx, "chrome")
        except Exception as e:  # Chrome missing / unlaunchable
            last_err = e
    try:
        ctx = pw.chromium.launch_persistent_context(**common)
        ctx.add_init_script(BROWSER_JS)
        return LaunchResult(ctx, "chromium")
    except Exception as e:
        # Chrome absent and bundled Chromium missing: fetch Chromium once
        # (spec section 3 fallback), then retry. Best-effort / 未検証.
        if _install_chromium():
            ctx = pw.chromium.launch_persistent_context(**common)
            ctx.add_init_script(BROWSER_JS)
            return LaunchResult(ctx, "chromium")
        raise RuntimeError(f"ブラウザを起動できませんでした: {e} (chrome: {last_err})")


def _install_chromium() -> bool:
    """Download the Chromium browser via Playwright's bundled driver (first-run
    fallback when the user has no Chrome). Returns True on success."""
    import subprocess
    try:
        from playwright._impl._driver import compute_driver_executable, get_driver_env
        exe = compute_driver_executable()
        cmd = list(exe) if isinstance(exe, (list, tuple)) else [exe]
        subprocess.run(cmd + ["install", "chromium"], env=get_driver_env(),
                       check=True, timeout=600)
        return True
    except Exception:
        return False
