"""Prove the REAL J-PlatPat capture is in page order - no repeats, no missing rows.

The boss's complaint is about the No. column repeating on
https://www.j-platpat.inpit.go.jp/t1201 searched with 音楽 (48,330 CSS px, 639
rows). The fixture test (test_stitch_order.py) proves the ordering exactly, but
on synthetic pages; this proves it on the page he actually used.

Method - ground truth, no OCR needed: after the extension has saved its image,
the page is put back into the exact state it was captured in and a handful of
viewports are re-shot at known scroll positions. Each one must appear in the
saved image at exactly that position. A repeated row shifts everything below it,
a skipped row shifts it the other way - either way the sampled viewport would no
longer line up, and the measured offset says by how much.

Captured at 1x so one saved CSS px == one image px and the comparison is exact.
"""
import base64
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
from patti_shot.jslib import BROWSER_JS

Image.MAX_IMAGE_PIXELS = None

HERE = os.path.dirname(os.path.abspath(__file__))
EXT = os.path.abspath(os.path.join(HERE, "..", "extension"))
WORK = os.path.join(os.environ["TEMP"], "patti_shot_align_test")
PROFILE = os.path.join(WORK, "profile")
DOWNLOADS = os.path.join(WORK, "downloads")
URL = "https://www.j-platpat.inpit.go.jp/t1201"
TERM = "音楽"
SAMPLES = 14
SEARCH = 300          # how far to look for the sample, px
STRIP = 400           # height of the compared strip, px


def grey(a):
    # every 8th column is plenty to identify a row and keeps the search fast
    a = a[:, ::8].astype(np.float32)
    return a[:, :, 0] * 0.299 + a[:, :, 1] * 0.587 + a[:, :, 2] * 0.114


def best_offset(page_strip, big, at):
    """Where in `big` does `page_strip` really sit, relative to `at`?"""
    h = page_strip.shape[0]
    lo = max(0, at - SEARCH)
    hi = min(big.shape[0] - h, at + SEARCH)
    if hi <= lo:
        return None, None
    a = grey(page_strip)
    win = grey(big[lo:hi + h])
    best, bestd = None, None
    for y in range(0, hi - lo + 1):
        d = float(np.abs(a - win[y:y + h]).mean())
        if bestd is None or d < bestd:
            bestd, best = d, lo + y
    return best - at, bestd


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

        # 1x + PNG only, so the saved image is 1:1 with CSS px
        sw = None
        for _ in range(60):
            sw = ctx.service_workers[0] if ctx.service_workers else None
            if sw:
                break
            time.sleep(0.5)
        ext_id = sw.url.split("/")[2]
        cfg = ctx.new_page()
        cfg.goto(f"chrome-extension://{ext_id}/popup.html")
        cfg.click("input[name='fmt'][value='png']")
        cfg.click("input[name='scale'][value='1']")
        time.sleep(1)
        cfg.close()

        print("[1] 『音楽』で検索...", flush=True)
        page.goto(URL, wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(2500)
        for sel in ("textarea", "input[type=text]"):
            done = False
            loc = page.locator(sel)
            for i in range(loc.count()):
                el = loc.nth(i)
                try:
                    if el.is_visible():
                        el.fill(TERM)
                        done = True
                        break
                except Exception:
                    continue
            if done:
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

        print("[2] 撮影...", flush=True)
        page.click("#patti-shot-fab")
        toast = ""
        for _ in range(360):
            time.sleep(2)
            toast = page.evaluate("""() => { const t=document.getElementById('patti-shot-toast');
                 return t && t.style.display !== 'none' ? t.textContent : ''; }""")
            if toast:
                break
        results["captured"] = "保存しました" in toast
        print("    " + " | ".join(toast.split("\n")), flush=True)

        for _ in range(180):
            if not glob.glob(os.path.join(DOWNLOADS, "*.crdownload")) \
               and glob.glob(os.path.join(DOWNLOADS, "*.png")):
                break
            time.sleep(2)
        time.sleep(3)
        pngs = sorted(glob.glob(os.path.join(DOWNLOADS, "*.png")))
        if not pngs:
            print("PNGなし -> FAIL")
            sys.exit(1)
        big = imaging.png_bytes_to_array(open(pngs[0], "rb").read())
        info = page.evaluate("""() => { try {
            return JSON.parse(document.documentElement.getAttribute('data-patti-shot-last') || '{}');
        } catch (e) { return {}; } }""")
        diag = info.get("diag", {})
        print(f"    保存画像 {big.shape[1]}x{big.shape[0]} / diag={diag}", flush=True)
        results["one_to_one"] = big.shape[1] == diag.get("cssW")

        # 2. put the page back into the captured state and re-shoot samples
        print("[3] 同じ状態に戻して照合...", flush=True)
        page.evaluate(BROWSER_JS)
        page.evaluate("() => window.__PATTISHOT__.prepare()")
        page.evaluate("() => window.__PATTISHOT__.neutralizeFixed()")
        page.evaluate("() => { const P = window.__PATTISHOT__; P._hideRestore = P._hideUI(); }")
        vp = 3600
        cdp.send("Emulation.setDeviceMetricsOverride",
                 {"width": diag["cssW"], "height": vp,
                  "deviceScaleFactor": 1, "mobile": False})
        page.wait_for_timeout(600)
        h = big.shape[0]

        offsets, diffs = [], []
        for i in range(SAMPLES):
            y = int((i + 0.5) * (h - vp) / SAMPLES)
            page.evaluate("(y) => window.__PATTISHOT__.scrollTo(y)", y)
            page.wait_for_timeout(500)
            act = page.evaluate("() => window.__PATTISHOT__.scrollY()")
            shot = cdp.send("Page.captureScreenshot",
                            {"format": "png", "captureBeyondViewport": False,
                             "fromSurface": True})
            arr = imaging.png_bytes_to_array(base64.b64decode(shot["data"]))
            top = 600                       # away from the viewport edges
            strip = arr[top:top + STRIP]
            at = int(round(act)) + top
            if at + STRIP > h or strip.shape[0] < STRIP:
                continue
            off, d = best_offset(strip, big, at)
            if off is None:
                continue
            offsets.append(off)
            diffs.append(d)
            print(f"    y={act:>6.0f}  ずれ={off:>+5d}px  差={d:5.1f}"
                  + ("  OK" if abs(off) <= 2 and d < 12 else "  ★NG"), flush=True)

        # [6] the boss's own check: the No. column. Every numbered cell is cut
        # out of the page and looked for in the saved image at the row it
        # belongs to. One repeated or dropped row would push every number below
        # it off by a row height, and this would say so.
        cells = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('*').forEach((e) => {
                if (e.children.length) return;
                const t = (e.textContent || '').trim();
                if (!/^\\d{1,4}$/.test(t)) return;
                const r = e.getBoundingClientRect();
                if (r.left > 260 || r.width < 8 || r.height < 8) return;
                out.push({ n: parseInt(t, 10), x: Math.round(r.left),
                           y: Math.round(r.top + window.__PATTISHOT__.scrollY()),
                           w: Math.round(r.width), h: Math.round(r.height) });
            });
            out.sort((a, b) => a.y - b.y);
            return out;
        }""")
        # the row list has more than one numeric column (No. and 区分), so keep
        # the one column whose values actually run 1,2,3,...
        by_x = {}
        for c in cells:
            by_x.setdefault(round(c["x"] / 4) * 4, []).append(c)
        cells = max(by_x.values(),
                    key=lambda g: len(g) if [c["n"] for c in g] == sorted(c["n"] for c in g)
                    else 0)
        seq = [c["n"] for c in cells]
        dom_ok = len(seq) > 100 and seq == sorted(seq) and len(set(seq)) == len(seq)
        print(f"[6] No.列を{len(seq)}個検出 {seq[:5]}...{seq[-3:]} "
              f"（ページ自身の並び: {'連番' if dom_ok else '不定'}）", flush=True)
        results["dom_rows"] = dom_ok

        bad, checked = [], 0
        step = max(1, len(cells) // 40)
        for c in cells[::step]:
            if c["y"] + c["h"] + 4 > big.shape[0]:
                continue
            page.evaluate("(y) => window.__PATTISHOT__.scrollTo(y)", max(0, c["y"] - 400))
            page.wait_for_timeout(180)
            act = page.evaluate("() => window.__PATTISHOT__.scrollY()")
            shot = cdp.send("Page.captureScreenshot",
                            {"format": "png", "captureBeyondViewport": False,
                             "fromSurface": True})
            arr = imaging.png_bytes_to_array(base64.b64decode(shot["data"]))
            ty = int(round(c["y"] - act))
            x0, x1 = max(0, c["x"] - 6), min(big.shape[1], c["x"] + c["w"] + 6)
            y0, y1 = max(0, ty - 4), min(arr.shape[0], ty + c["h"] + 4)
            if y1 - y0 < 8:
                continue
            live = arr[y0:y1, x0:x1].astype(np.float32)
            iy = c["y"] - 4
            saved = big[iy:iy + (y1 - y0), x0:x1].astype(np.float32)
            if saved.shape != live.shape:
                continue
            d = float(np.abs(live - saved).mean())
            checked += 1
            if d > 12:
                bad.append((c["n"], c["y"], round(d, 1)))
        results["numbers_in_place"] = checked >= 20 and not bad
        print(f"[7] No.セル {checked}個を画像上の同じ行と照合 -> 不一致 {len(bad)}件"
              + (f" {bad[:5]}" if bad else "")
              + f" -> {'PASS' if results['numbers_in_place'] else 'FAIL'}", flush=True)

        cdp.send("Emulation.clearDeviceMetricsOverride")
        page.evaluate("() => { const P = window.__PATTISHOT__; if (P._hideRestore) P._hideRestore(); P.restoreAll(); }")

        results["samples"] = len(offsets) >= SAMPLES - 2
        results["aligned"] = bool(offsets) and all(abs(o) <= 2 for o in offsets)
        results["matched"] = bool(diffs) and max(diffs) < 12
        worst = max((abs(o) for o in offsets), default=999)
        print(f"[4] 全{len(offsets)}地点の最大ずれ = {worst}px "
              f"(0なら1行の重複も欠落もない) -> {'PASS' if results['aligned'] else 'FAIL'}",
              flush=True)
        print(f"[5] 画素一致 最大差 = {max(diffs) if diffs else -1:.1f} -> "
              f"{'PASS' if results['matched'] else 'FAIL'}", flush=True)
        ctx.close()

    ok = all(results.values())
    print("JPLATPAT ALIGNMENT:", "PASS" if ok else f"FAIL {results}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
