"""Reproduce the boss's run: J-PlatPat 音楽 at HIS geometry, then check the file.

The previous tests ran in a ~1028 px wide window; his Chrome is 1920 CSS px
wide, which at 2x puts the assembled image past the 65,535 px canvas limit and
takes a different output path (PNG downscaled to one file, PDF split over 3
pages). His capture came back with rows 167/168 present twice, 546 CSS px apart.

This drives the real extension at 1920, then reads the saved PNG back and looks
for any row that appears twice - the boss's own criterion.
"""
import glob
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

Image.MAX_IMAGE_PIXELS = None

HERE = os.path.dirname(os.path.abspath(__file__))
# PATTI_SHOT_EXT lets this run an older build, to check whether a signature seen
# in the wild belongs to the version actually installed
EXT = os.environ.get("PATTI_SHOT_EXT") or os.path.abspath(os.path.join(HERE, "..", "extension"))
WORK = os.path.join(os.environ["TEMP"],
                    os.environ.get("PATTI_SHOT_WORK", "patti_shot_boss_test"))
PROFILE = os.path.join(WORK, "profile")
DOWNLOADS = os.path.join(WORK, "downloads")
URL = "https://www.j-platpat.inpit.go.jp/t1201"
TERM = "音楽"


def duplicate_report(img, css_scale):
    """Any band of rows that appears twice, at any distance (phase-independent).

    Works on a tall narrow slice of the row area: every 24-px window is hashed
    at several phases so a repeat is found no matter how far apart it is.
    """
    strip = max(8, int(round(12 * css_scale)))
    H, W = img.shape[0], img.shape[1]
    x0, x1 = int(W * 0.30), int(W * 0.75)
    band = img[:, x0:x1]
    grey = (band[:, :, 0] * 0.299 + band[:, :, 1] * 0.587 + band[:, :, 2] * 0.114)
    grey = grey[:, ::4].astype(np.float32)

    # signature per row, then look for runs of equal signatures far apart
    sig = np.round(grey / 12).astype(np.int16)
    keys = [hash(sig[y].tobytes()) for y in range(H)]
    first = {}
    hits = []
    for y, k in enumerate(keys):
        if sig[y].std() < 1.2:                 # blank / uniform row
            continue
        if k in first and y - first[k] > strip * 4:
            hits.append((first[k], y))
        else:
            first.setdefault(k, y)

    runs = []
    for a, b in hits:
        off = b - a
        if runs and runs[-1][2] == off and b == runs[-1][1] + 1:
            runs[-1][1] = b
        else:
            runs.append([b, b, off])
    runs = [r for r in runs if r[1] - r[0] >= strip * 2]
    runs.sort(key=lambda r: -(r[1] - r[0]))
    return runs


def main():
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(PROFILE, exist_ok=True)
    os.makedirs(DOWNLOADS, exist_ok=True)
    results = {}

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, channel="msedge", headless=False, no_viewport=True,
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}",
                  "--no-first-run", "--no-default-browser-check",
                  # the boss's plain Chrome may use the legacy screenshot path;
                  # Playwright force-enables the new one, so opt out to match
                  "--disable-features=CDPScreenshotNewSurface",
                  "--hide-crash-restore-bubble", "--window-size=1936,1040",
                  # this PC runs at 125% so a maximised window is only ~1532 CSS
                  # px wide; the boss's is 1920 at 100%. Forcing the ratio to 1
                  # reproduces BOTH his width and his devicePixelRatio, which is
                  # the variable the earlier tests never covered.
                  "--force-device-scale-factor=1",
                  "--window-position=0,0"],
            ignore_default_args=["--enable-automation", "--disable-extensions"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        cdp = ctx.new_cdp_session(page)
        cdp.send("Browser.setDownloadBehavior",
                 {"behavior": "allow", "downloadPath": DOWNLOADS})

        page.goto(URL, wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(2500)
        w = page.evaluate("() => window.innerWidth")
        h = page.evaluate("() => window.innerHeight")
        print(f"[0] ウィンドウ {w}x{h} css px（池本さんは1920幅）", flush=True)
        results["width_like_boss"] = w >= 1800

        for sel in ("textarea", "input[type=text]"):
            hit = False
            loc = page.locator(sel)
            for i in range(loc.count()):
                try:
                    el = loc.nth(i)
                    if el.is_visible():
                        el.fill(TERM)
                        hit = True
                        break
                except Exception:
                    continue
            if hit:
                break
        try:
            page.get_by_role("button", name="検索", exact=True).first.click(timeout=8000)
        except Exception:
            page.evaluate("""() => { const e = Array.from(document.querySelectorAll('button,a,span,div'))
                .find(x => (x.textContent||'').trim() === '検索' && x.offsetParent); if (e) e.click(); }""")
        try:
            page.wait_for_load_state("networkidle", timeout=120000)
        except Exception:
            pass
        page.wait_for_timeout(5000)
        page.wait_for_selector("#patti-shot-fab", timeout=60000)

        print("[1] 撮影...", flush=True)
        t0 = time.time()
        page.click("#patti-shot-fab")
        toast = ""
        last_prog = ""
        for i in range(900):                        # up to 30 minutes
            time.sleep(2)
            toast = page.evaluate("""() => { const t=document.getElementById('patti-shot-toast');
                 return t && t.style.display !== 'none' ? t.textContent : ''; }""")
            if toast:
                break
            if i % 15 == 14:                        # live heartbeat every 30s
                prog = page.evaluate("""() => document.documentElement
                    .getAttribute('data-patti-shot-progress') || ''""")
                if prog != last_prog:
                    print(f"    {time.time() - t0:.0f}s 進捗 {prog}", flush=True)
                    last_prog = prog
        results["captured"] = "保存しました" in toast
        print(f"    {time.time() - t0:.0f}秒 / " + " | ".join(toast.split("\n")), flush=True)

        info = page.evaluate("""() => { try {
            return JSON.parse(document.documentElement.getAttribute('data-patti-shot-last') || '{}');
        } catch (e) { return {}; } }""")
        diag = info.get("diag", {})
        print(f"    diag={diag}", flush=True)
        with open(os.path.join(WORK, "trace.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(info.get("trace", [])))
        print(f"    トレース: {os.path.join(WORK, 'trace.txt')} "
              f"({len(info.get('trace', []))}行)", flush=True)

        for _ in range(240):
            if not glob.glob(os.path.join(DOWNLOADS, "*.crdownload")) \
               and len(glob.glob(os.path.join(DOWNLOADS, "*.*"))) >= 2:
                break
            time.sleep(2)
        time.sleep(3)
        ctx.close()

    pngs = sorted(f for f in glob.glob(os.path.join(DOWNLOADS, "*.png")))
    if not pngs:
        print("PNGなし -> FAIL")
        sys.exit(1)
    img = imaging.png_bytes_to_array(open(pngs[0], "rb").read())
    css_scale = img.shape[1] / max(1, diag.get("cssW") or 1920)
    print(f"[2] PNG {img.shape[1]}x{img.shape[0]}（{css_scale:.2f}倍）", flush=True)

    runs = duplicate_report(img, css_scale)
    results["no_duplicate_rows"] = not runs
    print(f"[3] 二度出ている行のかたまり: {len(runs)}件 -> "
          f"{'PASS' if not runs else 'FAIL'}", flush=True)
    for s, e, off in runs[:15]:
        print(f"     y={s}..{e} ({e - s}px) は y={s - off} の再出現"
              f"（{off}px＝{off / css_scale:.0f}css px 離れ）", flush=True)

    ok = all(results.values())
    print("BOSS REPRO:", "PASS" if ok else f"FAIL {results}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
