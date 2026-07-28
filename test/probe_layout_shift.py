"""Does the page move under us while we capture it?

Absolute placement cannot duplicate a row - unless the row is at one document
position when one band is taken and a different position when the next one is.
So: replicate exactly what the capture does (prepare, neutralise fixed, emulate
the tall viewport, walk down), and after every step record where a few known
rows actually are. If those numbers move, that is the bug.

Run at the boss's window width (1920), which is where it goes wrong.
"""
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from playwright.sync_api import sync_playwright

from patti_shot.jslib import BROWSER_JS

WORK = os.path.join(os.environ["TEMP"], "patti_shot_shift_probe")
URL = "https://www.j-platpat.inpit.go.jp/t1201"
TERM = "音楽"

# document Y of the No. cells, keyed by the number they contain
MARKERS = """
() => {
  const out = [];
  const P = window.__PATTISHOT__;
  const sy = P.scrollY();
  document.querySelectorAll('*').forEach((e) => {
    if (e.children.length) return;
    const t = (e.textContent || '').trim();
    if (!/^\\d{1,4}$/.test(t)) return;
    const r = e.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) return;
    out.push([parseInt(t, 10), Math.round(r.left), Math.round(r.top + sy)]);
  });
  return out;
}
"""


def no_column(rows):
    """keep only the numeric column that actually runs 1,2,3,... (No.)"""
    by_x = {}
    for n, x, y in rows:
        by_x.setdefault(round(x / 4) * 4, []).append((n, y))
    best = []
    for g in by_x.values():
        g.sort(key=lambda t: t[1])
        nums = [n for n, _ in g]
        if nums == sorted(nums) and len(nums) > len(best):
            best = g
    return {n: y for n, y in best}


def main():
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            WORK, channel="chrome", headless=False,
            viewport={"width": 1920, "height": 950},
            args=["--no-first-run", "--no-default-browser-check"])
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

        # exactly what the extension does
        page.evaluate(BROWSER_JS)
        page.evaluate("() => window.__PATTISHOT__.prepare()")
        m = page.evaluate("() => window.__PATTISHOT__.measure()")
        print(f"prepare後: captureHeight={m['captureHeight']} viewport={m['viewport']}", flush=True)
        page.evaluate("() => window.__PATTISHOT__.neutralizeFixed()")
        vp = min(3600, max(900, round(m["viewport"])) * max(1, 4 // 2 + 1))
        cdp.send("Emulation.setDeviceMetricsOverride",
                 {"width": 1920, "height": vp, "deviceScaleFactor": 2, "mobile": False})
        page.wait_for_timeout(400)
        m2 = page.evaluate("() => window.__PATTISHOT__.measure()")
        finalH = round(m2["captureHeight"])
        print(f"擬似ビューポート {vp} -> captureHeight={finalH}", flush=True)

        overlap = max(40, round(vp * 0.08))
        step = max(100, vp - overlap)
        base = None
        moved = {}
        y = 0
        while y < finalH:
            page.evaluate("(y) => window.__PATTISHOT__.scrollTo(y)", y)
            page.wait_for_timeout(250)
            act = page.evaluate("() => window.__PATTISHOT__.scrollY()")
            h = page.evaluate("() => window.__PATTISHOT__.measure().captureHeight")
            marks = no_column(page.evaluate(MARKERS))
            if base is None:
                base = dict(marks)
            else:
                for k, v in marks.items():
                    if k in base and base[k] != v:
                        moved.setdefault(k, []).append((round(act), base[k], v))
                    base.setdefault(k, v)
            print(f"  y={y:>6} act={act:>7.0f} h={h:>6} 行={len(marks)} 動いた行={len(moved)}",
                  flush=True)
            y += step

        print("", flush=True)
        if not moved:
            print("★ 撮影中に行の位置は一切動いていない", flush=True)
        else:
            print(f"★ 撮影中に位置が動いた行: {len(moved)}件", flush=True)
            for k, v in list(moved.items())[:15]:
                first = v[0]
                print(f"   No.{k}: {first[1]} -> {first[2]} (差 {first[2] - first[1]}) "
                      f"@scroll {first[0]}", flush=True)
        cdp.send("Emulation.clearDeviceMetricsOverride")
        ctx.close()


if __name__ == "__main__":
    main()
