"""Prove the stitched image is in page order: nothing repeated, nothing skipped.

Height and blank checks pass even on a broken stitch, so this decodes the image
back into a sequence of row indices and checks it runs 0,1,2,... exactly once.

Two fixtures, because the two failures had different causes:
  ruler        - flat colour bands: caught the join landing 130 rows early
                 (1,871 duplicated rows)
  ruler_table  - hundreds of near-identical table rows, like the J-PlatPat
                 result list: caught the join matching the WRONG row, which
                 skipped whole chunks (the boss saw rows 21..62 missing)
"""
import glob
import os
import shutil
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
EXT = os.path.abspath(os.path.join(HERE, "..", "extension"))
WORK = os.path.join(os.environ["TEMP"], "patti_shot_order_test")

CASES = [
    ("ruler", 300, lambda i: (20 + (i // 16), 20 + (i % 16) * 14, 90), 0.75),
    ("ruler_table", 600, lambda i: (20 + (i // 25), 20 + (i % 25) * 9, 120), 0.006),
    ("ruler_lategrow", 600, lambda i: (20 + (i // 25), 20 + (i % 25) * 9, 120), 0.006),
]


def run_case(page, downloads, name, bands, colour_for, x_frac, imaging):
    for f in glob.glob(os.path.join(downloads, "*")):
        try:
            os.remove(f)
        except OSError:
            pass
    page.goto(f"{page._base}/{name}.html", wait_until="domcontentloaded", timeout=90000)
    page.wait_for_selector("#patti-shot-fab", timeout=30000)
    page_h = page.evaluate("() => document.documentElement.scrollHeight")
    print(f"--- {name}: {page_h} CSS px / {bands}行 ---", flush=True)

    page.click("#patti-shot-fab")
    toast = ""
    for _ in range(300):
        time.sleep(2)
        toast = page.evaluate("""() => { const t=document.getElementById('patti-shot-toast');
             return t && t.style.display!=='none' ? t.textContent : ''; }""")
        if toast:
            break
    ok_shot = "保存しました" in toast
    if not ok_shot:
        print("   撮影失敗:", toast, flush=True)
        return False

    info = page.evaluate("""() => { try {
        return JSON.parse(document.documentElement.getAttribute('data-patti-shot-last') || '{}');
    } catch (e) { return {}; } }""")
    forced = (info.get("diag") or {}).get("degradedBands", 0)
    for line in info.get("trace", []):
        if "伸びた" in line or "途中" in line:
            print("   " + line, flush=True)

    pngs = []
    for _ in range(30):
        pngs = [f for f in glob.glob(os.path.join(downloads, "*.png"))
                if not f.endswith(".crdownload")]
        if pngs:
            time.sleep(2)
            break
        time.sleep(1)
    if not pngs:
        print("   PNGなし -> FAIL", flush=True)
        return False

    img = imaging.png_bytes_to_array(open(sorted(pngs)[0], "rb").read())
    lookup = {colour_for(i): i for i in range(bands)}
    x = max(0, min(img.shape[1] - 1, int(img.shape[1] * x_frac)))
    seq, prev = [], None
    for y in range(img.shape[0]):
        idx = lookup.get(tuple(int(v) for v in img[y, x]))
        if idx is None:
            continue
        if idx != prev:
            seq.append(idx)
            prev = idx

    counts = {}
    for v in seq:
        counts[v] = counts.get(v, 0) + 1
    dups = sorted(v for v, c in counts.items() if c > 1)
    ascending = all(seq[i] < seq[i + 1] for i in range(len(seq) - 1))
    missing = sorted(set(range(bands)) - set(seq))
    covered = len(set(seq)) / bands
    ok = (not dups) and ascending and (not missing) and covered > 0.99 and forced == 0

    print(f"   画像 {img.shape[1]}x{img.shape[0]} / 読取 {len(seq)}行 "
          f"先頭{seq[:3]} 末尾{seq[-3:]}", flush=True)
    print(f"   重複={len(dups)}{dups[:5]} 昇順={ascending} 欠落={len(missing)}{missing[:5]} "
          f"網羅={covered:.1%} 強行継ぎ目={forced} -> {'PASS' if ok else 'FAIL'}", flush=True)
    return ok


def main():
    from patti_shot import imaging
    import fixtures as fx
    import functools, http.server, socketserver, threading

    shutil.rmtree(WORK, ignore_errors=True)
    profile = os.path.join(WORK, "profile")
    downloads = os.path.join(WORK, "dl")
    os.makedirs(profile, exist_ok=True)
    os.makedirs(downloads, exist_ok=True)
    fx.build_fixtures()

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    socketserver.ThreadingTCPServer.allow_reuse_address = True
    httpd = socketserver.ThreadingTCPServer(
        ("127.0.0.1", 0), functools.partial(Quiet, directory=os.path.join(HERE, "fixtures")))
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    results = {}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            profile, channel="msedge", headless=False, no_viewport=True,
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}",
                  "--no-first-run", "--no-default-browser-check"],
            ignore_default_args=["--enable-automation", "--disable-extensions"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page._base = base
        cdp = ctx.new_cdp_session(page)
        cdp.send("Browser.setDownloadBehavior",
                 {"behavior": "allow", "downloadPath": downloads})
        for name, bands, colour_for, x_frac in CASES:
            results[name] = run_case(page, downloads, name, bands, colour_for, x_frac, imaging)
        ctx.close()
    httpd.shutdown()

    ok = all(results.values())
    print("STITCH ORDER:", "PASS" if ok else f"FAIL {results}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
