"""Prove the stitched image is in page order: nothing repeated, nothing skipped.

The boss's failure looked like rows ...19, 20, then 9 again. Height and blank
checks all pass on such an image, so this test uses a fixture whose every 100px
band carries a colour encoding its index. The capture is decoded back into a
sequence of indices, which must run 0,1,2,... exactly once each.

That makes duplication and gaps impossible to miss, with no OCR and no guessing.
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
BANDS = 300


def colour_for(i):
    return (20 + (i // 16), 20 + (i % 16) * 14, 90)


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

    pngs = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            profile, channel="msedge", headless=False, no_viewport=True,
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}",
                  "--no-first-run", "--no-default-browser-check"],
            ignore_default_args=["--enable-automation", "--disable-extensions"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        cdp = ctx.new_cdp_session(page)
        cdp.send("Browser.setDownloadBehavior",
                 {"behavior": "allow", "downloadPath": downloads})

        page.goto(base + "/ruler.html", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("#patti-shot-fab", timeout=30000)
        page_h = page.evaluate("() => document.documentElement.scrollHeight")
        print(f"ページ: {page_h} CSS px（{BANDS}帯 x 100px）", flush=True)

        page.click("#patti-shot-fab")
        toast = ""
        for _ in range(300):
            time.sleep(2)
            toast = page.evaluate("""() => { const t=document.getElementById('patti-shot-toast');
                 return t && t.style.display!=='none' ? t.textContent : ''; }""")
            if toast:
                break
        print("toast:", " | ".join(toast.split("\n")), flush=True)

        tr = page.evaluate("""() => { try {
            return JSON.parse(document.documentElement.getAttribute('data-patti-shot-last') || '{}').trace || [];
        } catch (e) { return []; } }""")
        if tr:
            print(f"--- 撮影トレース ({len(tr)}回) 末尾10 ---", flush=True)
            for line in tr[-10:]:
                print("   ", line, flush=True)

        for _ in range(30):
            pngs = [f for f in glob.glob(os.path.join(downloads, "*.png"))
                    if not f.endswith(".crdownload")]
            if pngs:
                time.sleep(2)
                break
            time.sleep(1)
        ctx.close()
    httpd.shutdown()

    if not pngs:
        print("撮影できず -> FAIL")
        sys.exit(1)

    img = imaging.png_bytes_to_array(open(sorted(pngs)[0], "rb").read())
    print(f"画像: {img.shape[1]}x{img.shape[0]}", flush=True)

    # decode: walk down the image and read the band colour at a fixed column
    lookup = {colour_for(i): i for i in range(BANDS)}
    x = int(img.shape[1] * 0.75)          # right of the label text
    seq, prev = [], None
    for y in range(img.shape[0]):
        idx = lookup.get(tuple(int(v) for v in img[y, x]))
        if idx is None:
            continue
        if idx != prev:
            seq.append(idx)
            prev = idx

    print(f"読み取れた帯: {len(seq)}個 先頭={seq[:6]} 末尾={seq[-6:]}", flush=True)

    counts = {}
    for v in seq:
        counts[v] = counts.get(v, 0) + 1
    dups = sorted(v for v, c in counts.items() if c > 1)
    ascending = all(seq[i] < seq[i + 1] for i in range(len(seq) - 1))
    missing = sorted(set(range(min(seq), max(seq) + 1)) - set(seq)) if seq else []
    covered = len(set(seq)) / BANDS

    print(f"1 重複した帯: {len(dups)}個 {dups[:8]} -> {'PASS' if not dups else 'FAIL'}", flush=True)
    print(f"2 昇順（前に戻らない）: {'PASS' if ascending else 'FAIL'}", flush=True)
    print(f"3 抜けた帯: {len(missing)}個 {missing[:8]} -> {'PASS' if not missing else 'FAIL'}", flush=True)
    print(f"4 ページ全体: {len(set(seq))}/{BANDS}帯 ({covered:.0%}) -> "
          f"{'PASS' if covered > 0.97 else 'FAIL'}", flush=True)

    ok = (not dups) and ascending and (not missing) and covered > 0.97
    print("STITCH ORDER:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
