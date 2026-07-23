"""End-to-end app test: inject the floating UI + Python binding exactly as the
app does, click the pink FAB, and verify a full capture is saved (PNG+PDF) with
no injected UI in the output. No human interaction.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

OUT = os.path.join(os.environ["TEMP"], "patti_shot_app_out")
os.environ["PATTI_SHOT_OUT_DIR"] = OUT
os.environ["PATTI_SHOT_NO_OPEN"] = "1"

import json

from playwright.sync_api import sync_playwright
from PIL import Image

from patti_shot import browser, app, imaging
from patti_shot.ui import FLOATING_UI_JS, PINK
import fixtures as fx

Image.MAX_IMAGE_PIXELS = None
PROFILE = os.path.join(os.environ["TEMP"], "patti_shot_app_profile")
PINK_RGB = (int(PINK[1:3], 16), int(PINK[3:5], 16), int(PINK[5:7], 16))


def main():
    for f in glob.glob(os.path.join(OUT, "*")):
        os.remove(f)
    urls = fx.build_fixtures()
    ok = True
    with sync_playwright() as p:
        lr = browser.launch(p, PROFILE, headless=True, viewport={"width": 1280, "height": 900})
        ctx = lr.context
        ctx.add_init_script("window.__PATTISHOT_SETTINGS__ = {\"fmt\":\"both\",\"scale\":2};")
        ctx.add_init_script(FLOATING_UI_JS)
        page = ctx.new_page()
        page.goto(urls["tables"], wait_until="load", timeout=30000)
        page.wait_for_selector("#patti-shot-fab", timeout=10000)
        title_before = page.title()

        page.click("#patti-shot-fab")
        # act as the app's polling main loop: pick up the request, capture, reply
        served = False
        for _ in range(40):
            req = page.evaluate(app._GET_REQ)
            if req:
                data = json.loads(req)
                result = app.do_capture(page, data, lr.channel)
                result["id"] = data.get("id")
                page.evaluate("(r) => document.documentElement.setAttribute('data-patti-shot-result', r)",
                              json.dumps(result))
                served = True
                break
            page.wait_for_timeout(250)
        assert served, "capture request was never emitted by the FAB"
        # the UI polls the result and shows the toast
        page.wait_for_function(
            "() => { const t=document.getElementById('patti-shot-toast');"
            " return t && t.style.display!=='none' && /保存しました/.test(t.textContent); }",
            timeout=15000)
        toast = page.evaluate("() => document.getElementById('patti-shot-toast').textContent")
        title_after = page.title()
        ctx.close()

    pngs = glob.glob(os.path.join(OUT, "*.png"))
    pdfs = glob.glob(os.path.join(OUT, "*.pdf"))
    files_ok = len(pngs) >= 1 and len(pdfs) == 1
    print(f"toast: {toast!r}")
    print(f"files: png={len(pngs)} pdf={len(pdfs)} -> {'OK' if files_ok else 'NG'}")

    # UI must not be in the output
    leak = 0
    if pngs:
        arr = imaging.png_bytes_to_array(open(sorted(pngs)[0], "rb").read())
        leak = imaging.count_color(arr, PINK_RGB)
    leak_ok = leak < 500
    print(f"ui_leak: pink_px={leak} -> {'OK' if leak_ok else 'NG'}")

    title_ok = title_before == title_after
    print(f"title restored: {title_before!r} == {title_after!r} -> {'OK' if title_ok else 'NG'}")

    ok = files_ok and leak_ok and title_ok
    print("APP VERIFICATION:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
