"""What exactly differs between two overlapping captures of J-PlatPat?

The extension's verifier reported a constant 18.75% row mismatch between every
band and the previous band's tail - at the CORRECT position. Something is in
one capture but not the other. This reproduces the exact comparison and saves
side-by-side crops of the mismatching rows, so the artifact can be SEEN.
"""
import base64
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np
from playwright.sync_api import sync_playwright
from PIL import Image

from patti_shot import imaging
from patti_shot.jslib import BROWSER_JS

WORK = os.path.join(os.environ["TEMP"], "patti_shot_artifact_probe")
URL = "https://www.j-platpat.inpit.go.jp/t1201"
TERM = "音楽"
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(WORK, "out")


def main():
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            WORK + "\\profile", channel="msedge", headless=False, no_viewport=True,
            args=["--no-first-run", "--no-default-browser-check",
                  "--window-size=1936,1040", "--force-device-scale-factor=1",
                  "--window-position=0,0"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        cdp = ctx.new_cdp_session(page)
        page.goto(URL, wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(2500)
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

        # exactly what the extension does before the walk
        page.evaluate(BROWSER_JS)
        page.evaluate("() => window.__PATTISHOT__.prepare()")
        page.evaluate("() => window.__PATTISHOT__.neutralizeFixed()")
        page.evaluate("() => window.__PATTISHOT__.guardPointer()")
        m = page.evaluate("() => window.__PATTISHOT__.measure()")
        vp = min(3600, max(900, round(m["viewport"])) * 3)
        cdp.send("Emulation.setDeviceMetricsOverride",
                 {"width": 1912, "height": vp, "deviceScaleFactor": 2, "mobile": False})
        page.wait_for_timeout(500)

        def shot_at(css_y):
            page.evaluate("(y) => window.__PATTISHOT__.scrollTo(y)", css_y)
            page.wait_for_timeout(400)
            act = page.evaluate("() => window.__PATTISHOT__.scrollY()")
            d = cdp.send("Page.captureScreenshot",
                         {"format": "png", "captureBeyondViewport": False,
                          "fromSurface": True})
            return act, imaging.png_bytes_to_array(base64.b64decode(d["data"]))

        step = vp - max(40, round(vp * 0.08))
        a_act, a_img = shot_at(0)
        b_act, b_img = shot_at(step)
        print(f"vp={vp} step={step} act A={a_act} B={b_act}", flush=True)
        print(f"A {a_img.shape} B {b_img.shape}", flush=True)

        # band B's top overlaps band A's rows [round(b_act*2) .. A_height)
        top_in_a = int(round(b_act * 2))
        ov = a_img.shape[0] - top_in_a
        A = a_img[top_in_a:].astype(np.int16)
        B = b_img[:ov].astype(np.int16)
        print(f"overlap {ov} device rows", flush=True)

        grey_a = (A[:, :, 0] * 77 + A[:, :, 1] * 151 + A[:, :, 2] * 28) >> 8
        grey_b = (B[:, :, 0] * 77 + B[:, :, 1] * 151 + B[:, :, 2] * 28) >> 8
        diff = np.abs(grey_a - grey_b)
        x0, x1 = 4, a_img.shape[1] - 44
        bad = (diff[:, x0:x1] > 28)
        bad_per_row = bad.sum(axis=1)
        bad_rows = np.where(bad_per_row >= 5)[0]
        print(f"不一致行: {len(bad_rows)} / {ov} ({len(bad_rows)/ov:.1%})", flush=True)
        if len(bad_rows):
            runs = []
            for v in bad_rows:
                if runs and v <= runs[-1][1] + 3:
                    runs[-1][1] = v
                else:
                    runs.append([v, v])
            print("不一致行のかたまり:", runs[:12], flush=True)
            # which columns?
            bad_cols = bad[bad_rows].sum(axis=0)
            hot = np.where(bad_cols > len(bad_rows) * 0.3)[0]
            print(f"不一致が集中する列: x={x0+hot.min() if len(hot) else '-'}"
                  f"..{x0+hot.max() if len(hot) else '-'}", flush=True)
            # save side-by-side crops of the first big run
            s, e = max(runs, key=lambda r: r[1] - r[0])
            pad = 40
            ca = A[max(0, s-pad):e+pad].clip(0, 255).astype(np.uint8)
            cb = B[max(0, s-pad):e+pad].clip(0, 255).astype(np.uint8)
            sep = np.full((ca.shape[0], 16, 3), 255, np.uint8); sep[:, 6:10] = 0
            pair = np.hstack([ca, sep, cb])
            im = Image.fromarray(pair)
            if im.width > 4000:
                im = im.resize((im.width // 2, im.height // 2))
            im.save(os.path.join(OUT, "diffpair.png"))
            dm = (bad * 255).astype(np.uint8)
            Image.fromarray(dm).resize((dm.shape[1] // 4, max(1, dm.shape[0] // 4))).save(
                os.path.join(OUT, "diffmap.png"))
            print("保存:", OUT, flush=True)
        ctx.close()


if __name__ == "__main__":
    main()
