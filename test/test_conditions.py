"""Verify completion conditions 4-6 (spec section 9).

  4. login/state persists across app restarts (persistent profile).
  5. a 2x PDF stays readable (Japanese) when zoomed.
  6. 10 consecutive captures: no crash, no runaway memory.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np
import psutil
import fitz  # pymupdf
from playwright.sync_api import sync_playwright

from patti_shot import browser, engine, output, util, imaging
import fixtures as fx

TMP = os.environ["TEMP"]
PERSIST_PROFILE = os.path.join(TMP, "patti_shot_persist_profile")
LOOP_PROFILE = os.path.join(TMP, "patti_shot_loop_profile")
OUT = os.path.join(TMP, "patti_shot_cond_out")


def cond4_login_persist(p):
    """Set a persistent cookie, close, relaunch, confirm it survived."""
    lr = browser.launch(p, PERSIST_PROFILE, headless=True, viewport={"width": 1000, "height": 800})
    lr.context.add_cookies([{
        "name": "patti_login", "value": "session-abc-123",
        "domain": "example.com", "path": "/",
        "expires": 4102444800,  # year 2100
    }])
    lr.context.close()
    lr2 = browser.launch(p, PERSIST_PROFILE, headless=True, viewport={"width": 1000, "height": 800})
    cookies = {c["name"]: c["value"] for c in lr2.context.cookies("https://example.com/")}
    lr2.context.close()
    ok = cookies.get("patti_login") == "session-abc-123"
    print(f"[4] login-persist: cookie after relaunch = {cookies.get('patti_login')!r} -> {'PASS' if ok else 'FAIL'}")
    return ok


def cond5_pdf_readable(p, urls):
    """2x PDF of a Japanese page: render back and confirm sharp text detail."""
    lr = browser.launch(p, LOOP_PROFILE, headless=True, viewport={"width": 1280, "height": 900})
    page = lr.context.new_page()
    page.goto(urls["japanese"], wait_until="load", timeout=30000)
    r = engine.capture(page, scale=2)
    lr.context.close()
    os.makedirs(OUT, exist_ok=True)
    pdf = output.save_pdf(r.array, os.path.join(OUT, "japanese_2x"), r.scale)
    doc = fitz.open(pdf)
    pg = doc[0]
    # render the PDF page at 2x zoom and measure fine-detail contrast
    pix = pg.get_pixmap(matrix=fitz.Matrix(2, 2))
    ren = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
    detail = float(ren.astype(np.float32).std())
    # count dark (ink) pixels -> text is actually present, not a blank page
    ink = float((ren.mean(axis=2) < 128).mean()) * 100
    doc.close()
    ok = detail > 25 and ink > 0.3
    print(f"[5] pdf-readable(2x,JP): render_detail_std={detail:.1f} ink_coverage={ink:.2f}% "
          f"-> {'PASS' if ok else '未検証/FAIL'}  (可読性の最終判断は目視推奨)")
    return ok


def cond6_stress(p, urls):
    """10 consecutive captures; no crash, memory not runaway, all valid."""
    proc = psutil.Process()
    lr = browser.launch(p, LOOP_PROFILE, headless=True, viewport={"width": 1280, "height": 900})
    page = lr.context.new_page()
    page.goto(urls["tables"], wait_until="load", timeout=30000)
    rss0 = proc.memory_info().rss / 1e6
    bad = 0
    for i in range(10):
        # reuse_buffer=True mirrors how the app captures (result consumed before
        # the next capture)
        r = engine.capture(page, scale=2, reuse_buffer=True)
        if r.array is None or r.width_px < 10 or imaging.blank_runs(r.array, scale=r.scale):
            bad += 1
        del r
        util.release_memory()
    rss1 = proc.memory_info().rss / 1e6
    lr.context.close()
    growth = rss1 - rss0
    ok = bad == 0 and growth < 400
    print(f"[6] stress x10: invalid={bad}/10 rss {rss0:.0f}->{rss1:.0f}MB (growth {growth:+.0f}MB) "
          f"-> {'PASS' if ok else 'FAIL'}")
    return ok


def main():
    urls = fx.build_fixtures()
    with sync_playwright() as p:
        r4 = cond4_login_persist(p)
        r5 = cond5_pdf_readable(p, urls)
        r6 = cond6_stress(p, urls)
    ok = r4 and r5 and r6
    print("CONDITIONS 4-6:", "PASS" if ok else "SEE ABOVE")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
