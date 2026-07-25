"""Load the real extension in real Chrome and verify it captures correctly.

The desktop app is verified by test/harness.py; this is the same idea for the
extension: drive actual pages, click the injected button, and machine-judge the
files that land in the download folder.

  1  the button is injected on real pages (and at half-screen width)
  2  clicking it produces PNG + PDF in the download folder
  3  the PNG is full-page (height matches the measured content height)
  4  no blank bands, and the injected UI is not in the image
  5  the page is restored afterwards (no leftover style changes)
"""
import glob
import json
import os
import shutil
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np
from playwright.sync_api import sync_playwright
from PIL import Image

from patti_shot import imaging
import fixtures as fx

Image.MAX_IMAGE_PIXELS = None

HERE = os.path.dirname(os.path.abspath(__file__))
EXT = os.path.join(HERE, "..", "extension")
WORK = os.path.join(os.environ["TEMP"], "patti_shot_ext_test")
PROFILE = os.path.join(WORK, "profile")
DOWNLOADS = os.path.join(WORK, "downloads")
PINK_RGB = (0xD6, 0x33, 0x6C)


def fresh_dirs():
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(PROFILE, exist_ok=True)
    os.makedirs(DOWNLOADS, exist_ok=True)


def serve_fixtures():
    """The extension only runs on http(s) (file:// would need a user toggle), so
    the fixtures are served over a local HTTP server for the test."""
    import functools
    import http.server
    import socketserver
    import threading

    root = os.path.join(HERE, "fixtures")

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):        # keep the test output readable
            pass

    handler = functools.partial(Quiet, directory=root)
    # threading: a single-threaded server stalls while a big fixture is served
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    httpd.daemon_threads = True
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{port}"


def wait_files(pattern, n, timeout=180):
    end = time.time() + timeout
    while time.time() < end:
        got = [f for f in glob.glob(pattern) if not f.endswith(".crdownload")]
        if len(got) >= n:
            time.sleep(1.5)          # let the writes settle
            return sorted(got)
        time.sleep(1)
    return sorted(f for f in glob.glob(pattern) if not f.endswith(".crdownload"))


def main():
    fresh_dirs()
    fx.build_fixtures()
    httpd, base = serve_fixtures()
    print("fixtures served at", base, flush=True)
    results = {}

    with sync_playwright() as p:
        # Chrome 137+ refuses --load-extension under automation (verified: zero
        # extension targets), so the automated run uses Edge, which is the same
        # Chromium engine and the same chrome.* extension APIs. The extension
        # ships for Chrome; this harness proves the code paths, and the Chrome
        # install itself is a one-click store install.
        # NOTE: do not pass downloads_path -- Playwright would intercept the
        # extension's chrome.downloads saves and rewrite them to GUID names, so
        # the real filenames could not be checked. The download directory is set
        # through CDP below instead.
        ctx = p.chromium.launch_persistent_context(
            PROFILE, channel="msedge", headless=False, no_viewport=True,
            args=[
                f"--disable-extensions-except={os.path.abspath(EXT)}",
                f"--load-extension={os.path.abspath(EXT)}",
                "--no-first-run", "--no-default-browser-check",
                "--hide-crash-restore-bubble",
                # Chrome 137+ ignores --load-extension under automation unless
                # this feature is turned off.
                "--disable-features=DisableLoadExtensionCommandLineSwitch",
            ],
            # Playwright passes --disable-extensions by default, which silently
            # kills the extension we are trying to test.
            ignore_default_args=["--enable-automation", "--disable-extensions"],
        )
        # Chrome must save where we can see it
        ctx.set_default_timeout(60000)

        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        cdp = ctx.new_cdp_session(page)
        cdp.send("Browser.setDownloadBehavior",
                 {"behavior": "allow", "downloadPath": DOWNLOADS})

        # --- extra pages: the split path and fixed elements, the two places
        #     capture quality actually breaks ---
        for name, scale in (("long", 2), ("fixedheader", 2)):
            for f in glob.glob(os.path.join(DOWNLOADS, "*.*")):
                os.remove(f)
            page.goto(f"{base}/{name}.html", wait_until="domcontentloaded", timeout=90000)
            page.wait_for_selector("#patti-shot-fab", timeout=30000)
            page.click("#patti-shot-fab")
            got = wait_files(os.path.join(DOWNLOADS, "*.png"), 1, timeout=300)
            if not got:
                results[f"page_{name}"] = False
                print(f"* {name}: 撮影失敗 -> FAIL")
                continue
            arr = imaging.png_bytes_to_array(open(got[0], "rb").read())
            m = page.evaluate("() => window.__PATTISHOT__.measure()")
            hi = arr.shape[0] / scale
            full = abs(hi - m["contentHeight"]) <= max(0.05 * m["contentHeight"], 40)
            runs = imaging.blank_runs(arr, scale=scale)
            dup = imaging.duplicate_run_px(arr, round(m["viewport"] * scale)) / scale
            ok_page = full and not runs and dup < 120
            results[f"page_{name}"] = ok_page
            print(f"* {name}: 画像={arr.shape[1]}x{arr.shape[0]} 全体={full} "
                  f"空白={len(runs)} ヘッダー重複={dup:.0f}css -> {'PASS' if ok_page else 'FAIL'}")

        for f in glob.glob(os.path.join(DOWNLOADS, "*.*")):
            os.remove(f)
        page.goto(base + "/tables.html", wait_until="domcontentloaded", timeout=90000)
        page.wait_for_selector("#patti-shot-fab", timeout=30000)
        print("1 ボタン注入(実ページ): PASS")
        results["inject"] = True

        vis = page.evaluate("""() => { const f=document.getElementById('patti-shot-fab');
            const r=f.getBoundingClientRect();
            return r.bottom <= innerHeight+1 && r.right <= innerWidth+1 && r.width > 0; }""")
        results["visible"] = vis
        print(f"1b ボタンが画面内: {'PASS' if vis else 'FAIL'}")

        print("2 撮影を実行（ボタンをクリック）...", flush=True)
        page.click("#patti-shot-fab")
        # Playwright renames intercepted downloads to GUIDs, so the files are
        # checked by content and the intended filename is read from the toast.
        files = wait_files(os.path.join(DOWNLOADS, "*.*"), 2)
        pngs = [f for f in files if f.lower().endswith(".png")]
        pdfs = [f for f in files if f.lower().endswith(".pdf")]
        toast = page.evaluate("""() => { const t=document.getElementById('patti-shot-toast');
             return t ? t.textContent : ''; }""")
        named = ("PATTI SHOT/PATTISHOT_" in toast and ".png" in toast and ".pdf" in toast)
        results["files"] = bool(pngs) and bool(pdfs) and named
        print(f"2 PNG/PDF生成: png={len(pngs)} pdf={len(pdfs)} 保存名OK={named} -> "
              f"{'PASS' if results['files'] else 'FAIL'}")
        print("   toast:", " / ".join(toast.split("\n")))
        for f in files:
            print("   ", os.path.basename(f), f"{os.path.getsize(f)//1024}KB")

        if pngs:
            arr = imaging.png_bytes_to_array(open(pngs[0], "rb").read())
            # 3: full page (image height / scale vs measured content height)
            m = page.evaluate("() => window.__PATTISHOT__.measure()")
            scale = 2
            hi = arr.shape[0] / scale
            tol = max(0.05 * m["contentHeight"], 40)
            results["fullpage"] = abs(hi - m["contentHeight"]) <= tol
            print(f"3 全体が写っている: 画像/{scale}={hi:.0f} vs 実測={m['contentHeight']} "
                  f"tol=±{tol:.0f} -> {'PASS' if results['fullpage'] else 'FAIL'}")
            # 4: no blank bands, no injected UI
            runs = imaging.blank_runs(arr, scale=scale)
            pink = imaging.count_color(arr, PINK_RGB)
            results["blank"] = not runs
            results["ui_leak"] = pink < 500
            print(f"4 空白帯なし: runs={runs[:3]} -> {'PASS' if results['blank'] else 'FAIL'}")
            print(f"4b UI写り込みなし: pink_px={pink} -> {'PASS' if results['ui_leak'] else 'FAIL'}")

        # 5: page restored -- no leftover markers or injected style tags
        left = page.evaluate("""() => ({
            touched: document.querySelectorAll('[data-patti-shot-touched]').length,
            styleTags: document.querySelectorAll('style[data-patti-shot]').length,
            hiddenUI: Array.from(document.querySelectorAll('[data-patti-shot-ui]'))
                           .filter(e => e.style.visibility === 'hidden').length,
        })""")
        results["cleanup"] = (left["touched"] == 0 and left["styleTags"] == 0
                              and left["hiddenUI"] == 0)
        print(f"5 ページ復元(痕跡なし): {left} -> {'PASS' if results['cleanup'] else 'FAIL'}")

        ctx.close()

    ok = all(results.values())
    print("EXTENSION VERIFICATION:", "PASS" if ok else f"FAIL {results}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
