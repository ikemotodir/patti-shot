"""The boss's real failing case: J-PlatPat 商品･役務名検索 with 音楽.

Measured at 48,469 CSS px -- 96,938 px at 2x, past Chrome's 65,535 px canvas
limit, which is what produced "The size of OffscreenCanvas is zero".

Drives the actual extension through the actual search and checks the saved
files: the capture must succeed, cover the whole page, contain no blank bands
and no duplicated header.
"""
import glob
import os
import shutil
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from playwright.sync_api import sync_playwright
from PIL import Image

from patti_shot import imaging

Image.MAX_IMAGE_PIXELS = None

HERE = os.path.dirname(os.path.abspath(__file__))
EXT = os.path.abspath(os.path.join(HERE, "..", "extension"))
WORK = os.path.join(os.environ["TEMP"], "patti_shot_huge_test")
PROFILE = os.path.join(WORK, "profile")
DOWNLOADS = os.path.join(WORK, "downloads")
URL = "https://www.j-platpat.inpit.go.jp/t1201"
TERM = "音楽"


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
                  "--hide-crash-restore-bubble"],
            ignore_default_args=["--enable-automation", "--disable-extensions"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        cdp = ctx.new_cdp_session(page)
        cdp.send("Browser.setDownloadBehavior",
                 {"behavior": "allow", "downloadPath": DOWNLOADS})

        print("[1] 検索ページを開いて『音楽』で検索...", flush=True)
        page.goto(URL, wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(2500)
        filled = False
        for sel in ("textarea", "input[type=text]"):
            loc = page.locator(sel)
            for i in range(loc.count()):
                try:
                    el = loc.nth(i)
                    if el.is_visible():
                        el.fill(TERM)
                        filled = True
                        break
                except Exception:
                    continue
            if filled:
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
        # NOTE: scrollHeight before the capture is short -- this page grows as the
        # engine forces its lazy content to render, so the real height is only
        # known after prepare(). Measure it the way the engine does.
        from patti_shot.jslib import BROWSER_JS
        page.evaluate(BROWSER_JS)
        page.evaluate("() => window.__PATTISHOT__.prepare()")
        h = page.evaluate("() => window.__PATTISHOT__.measure().contentHeight")
        page.evaluate("() => window.__PATTISHOT__.restoreAll()")
        print(f"    実コンテンツ高さ: {h} CSS px（2倍なら {h*2} px / canvas上限は65535）", flush=True)
        results["long_enough"] = h > 20000

        print("[2] 撮影（時間がかかります）...", flush=True)
        t0 = time.time()
        page.click("#patti-shot-fab")
        toast = ""
        for _ in range(360):          # up to 12 minutes
            time.sleep(2)
            toast = page.evaluate("""() => { const t=document.getElementById('patti-shot-toast');
                 return t && t.style.display !== 'none' ? t.textContent : ''; }""")
            if toast:
                break
        elapsed = time.time() - t0
        ok_toast = "保存しました" in toast
        results["captured"] = ok_toast
        print(f"    {elapsed:.0f}秒 / toast: " + " | ".join(toast.split("\n")), flush=True)

        # a 65,000 px PNG takes a while to write -- wait for the downloads to
        # finish (no .crdownload left) before judging the files
        for _ in range(180):
            pending = glob.glob(os.path.join(DOWNLOADS, "*.crdownload"))
            done = [f for f in glob.glob(os.path.join(DOWNLOADS, "*.*"))
                    if not f.endswith(".crdownload")]
            if not pending and len(done) >= 2:
                break
            time.sleep(2)
        time.sleep(2)
        files = sorted(f for f in glob.glob(os.path.join(DOWNLOADS, "*.*"))
                       if not f.endswith(".crdownload"))
        pngs = [f for f in files if f.lower().endswith(".png")]
        pdfs = [f for f in files if f.lower().endswith(".pdf")]
        print(f"    PNG={len(pngs)}枚 PDF={len(pdfs)}個", flush=True)
        for f in files:
            print(f"      {os.path.basename(f)} {os.path.getsize(f)//1024}KB", flush=True)
        results["files"] = bool(pngs) and bool(pdfs)

        # the saved PNGs must cover the page and be clean. The PNG may be scaled
        # down to fit one file, so measure coverage in CSS px using its own width.
        css_w = page.evaluate("() => window.innerWidth")
        total_css = 0.0
        blank_total = 0
        for f in pngs:
            arr = imaging.png_bytes_to_array(open(f, "rb").read())
            png_scale = arr.shape[1] / css_w           # width -> effective scale
            total_css += arr.shape[0] / png_scale
            blank_total += len(imaging.blank_runs(arr, scale=max(1, round(png_scale))))
            print(f"    PNG {arr.shape[1]}x{arr.shape[0]} (約{png_scale:.2f}倍)", flush=True)
        results["covers_page"] = total_css >= h * 0.95
        results["no_blank"] = blank_total == 0
        print(f"[3] 画像のCSS px換算高さ = {total_css:.0f} vs ページ {h} -> "
              f"{'PASS' if results['covers_page'] else 'FAIL'}", flush=True)
        print(f"[4] 空白帯: {blank_total} -> {'PASS' if results['no_blank'] else 'FAIL'}", flush=True)

        # [6] duplication: the boss saw the same row numbers repeating, which is
        # what a misaligned stitch looks like. Two independent checks:
        #   a) no long run of rows that repeats one viewport later
        #   b) no two distant slices of the image that are identical
        if pngs:
            import numpy as np
            arr = imaging.png_bytes_to_array(open(pngs[0], "rb").read())
            png_scale = arr.shape[1] / css_w
            dup = imaging.duplicate_run_px(arr, round(900 * png_scale)) / png_scale
            results["no_dup_run"] = dup < 120
            print(f"[6a] 同じ行の繰り返し: {dup:.0f}css px -> "
                  f"{'PASS' if results['no_dup_run'] else 'FAIL'}", flush=True)

            # Identical strips far apart. A page legitimately repeats small
            # UI (the search form stacks identical checkbox rows), so only a
            # stitch-sized repeat counts: the strip must be tall and the gap
            # must be about a captured band, which is what a misaligned stitch
            # produces.
            band_px = 3600 * png_scale               # emulated capture band
            strip = max(40, int(120 * png_scale))
            seen, repeats, worst = {}, 0, None
            for y in range(0, arr.shape[0] - strip, strip):
                block = arr[y:y + strip]
                if block.std() < 12:                 # skip near-uniform strips
                    continue
                key = hash(block.tobytes())
                prev = seen.get(key)
                if prev is not None and (y - prev) > band_px * 0.5:
                    repeats += 1
                    if worst is None:
                        worst = (prev, y)
                seen[key] = y
            results["no_repeat_strips"] = repeats == 0
            print(f"[6b] 貼り合わせ由来の重複: {repeats}件"
                  + (f"（例: y={worst[0]} と y={worst[1]}）" if worst else "")
                  + f" -> {'PASS' if results['no_repeat_strips'] else 'FAIL'}", flush=True)

        # PDF must have real pages
        if pdfs:
            import fitz
            doc = fitz.open(pdfs[0])
            results["pdf_pages"] = doc.page_count >= 1
            print(f"[5] PDF: {doc.page_count}ページ -> PASS", flush=True)
            doc.close()

        ctx.close()

    ok = all(results.values())
    print("HUGE PAGE VERIFICATION:", "PASS" if ok else f"FAIL {results}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
