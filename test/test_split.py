"""Correctness proof for tall-page capture (spec STEP3).

captureBeyondViewport is silently wrong beyond Chrome's ~16384px surface limit,
so tall pages use scroll-stitch (each viewport screenshotted on-screen). This
verifies:
  A. the scroll-stitched output matches fresh on-screen ground truth at every
     sampled position, INCLUDING beyond 16384px (no gap / overlap / drift).
  B. a fixed-header page split shows no blank, no header duplication, clean
     restore.
"""
import os, sys, base64
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np
from playwright.sync_api import sync_playwright

from patti_shot import browser, engine, imaging
from patti_shot.ui import FLOATING_UI_JS
import fixtures as fx

PROFILE = os.path.join(os.environ["TEMP"], "patti_shot_split_profile")


def onscreen(cdp):
    r = cdp.send("Page.captureScreenshot",
                 {"format": "png", "captureBeyondViewport": False, "fromSurface": True})
    return imaging.png_bytes_to_array(base64.b64decode(r["data"]))


def main():
    urls = fx.build_fixtures()
    ok = True
    with sync_playwright() as p:
        lr = browser.launch(p, PROFILE, headless=True, viewport={"width": 1280, "height": 900})
        lr.context.add_init_script(FLOATING_UI_JS)
        page = lr.context.new_page()

        # A. scroll-stitch vs on-screen ground truth (scale=1, no fixed elems)
        page.goto(urls["long"], wait_until="load", timeout=30000)
        r = engine.capture(page, scale=1, force_band_css=1500)  # force scroll-stitch
        out = r.array
        # rebuild the prepared layout and sample the live viewport at several y
        page.evaluate("() => window.__PATTISHOT__.prepare()")
        page.evaluate("() => { window.__PATTISHOT__._t = window.__PATTISHOT__._hideUI(); }")
        cdp = page.context.new_cdp_session(page)
        worst = 0.0
        checked = []
        try:
            for y in [0, 5000, 12000, 17000, 20000]:
                if y > out.shape[0] - 200:
                    continue
                page.evaluate("(yy) => window.scrollTo(0, yy)", y)
                actual = int(page.evaluate("() => window.scrollY"))
                shot = onscreen(cdp)
                seg = out[actual:actual + shot.shape[0]]
                h = min(seg.shape[0], shot.shape[0]); w = min(seg.shape[1], shot.shape[1])
                d = float(np.abs(seg[:h, :w].astype(np.int16) - shot[:h, :w].astype(np.int16)).mean())
                worst = max(worst, d)
                checked.append((actual, round(d, 2)))
        finally:
            page.evaluate("() => { window.__PATTISHOT__._t && window.__PATTISHOT__._t(); }")
            cdp.detach()
        a_ok = r.split and worst < 1.0
        print(f"A truth-match: bands={r.bands} img={out.shape} worst_diff={worst:.3f} "
              f"samples={checked} -> {'PASS' if a_ok else 'FAIL'}")
        ok &= a_ok

        # B. fixed-header page, forced split
        page.goto(urls["fixedheader"], wait_until="load", timeout=30000)
        sig_before = page.evaluate("() => window.__PATTISHOT__.styleSignature()")
        b = engine.capture(page, scale=2, force_band_css=900)
        sig_after = page.evaluate("() => window.__PATTISHOT__.styleSignature()")
        dup = imaging.duplicate_run_px(b.array, round(b.measurement.viewport * b.scale)) / b.scale
        b_ok = (b.split and not b.blank_runs and dup < 120 and sig_before == sig_after)
        print(f"B fixed-split: bands={b.bands} blank={b.blank_runs[:2]} dup={dup:.0f}css "
              f"cleanup={sig_before == sig_after} -> {'PASS' if b_ok else 'FAIL'}")
        ok &= b_ok

        lr.context.close()
    print("SPLIT VERIFICATION:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
