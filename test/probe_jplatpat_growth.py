"""Why did the boss's capture stop at 2,967 px when the page is 48,330?

J-PlatPat renders its result rows as you scroll, so the engine's prepare() has
to walk the page to make them exist before the height is measured. This logs how
the height actually grows during that walk, so the truncation can be seen rather
than guessed at.
"""
import os
import shutil
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from playwright.sync_api import sync_playwright

from patti_shot.jslib import BROWSER_JS

WORK = os.path.join(os.environ["TEMP"], "patti_shot_growth_probe")
URL = "https://www.j-platpat.inpit.go.jp/t1201"
TERM = "音楽"

WALK = """
async () => {
  const log = [];
  const de = document.scrollingElement;
  const step = Math.max(200, Math.floor(window.innerHeight * 0.85));
  const raf = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const wait = (ms) => new Promise(r => setTimeout(r, ms));
  let pos = 0, guard = 0;
  log.push(`start h=${de.scrollHeight} vp=${window.innerHeight} step=${step}`);
  while (guard++ < 2000) {
    window.scrollTo({ top: pos, left: 0, behavior: 'instant' });
    await raf(); await wait(80);
    const max = de.scrollHeight - window.innerHeight;
    if (guard <= 12 || guard % 10 === 0)
      log.push(`#${guard} pos=${pos} h=${de.scrollHeight} max=${max}`);
    if (pos >= max) { log.push(`#${guard} STOP pos=${pos} >= max=${max} h=${de.scrollHeight}`); break; }
    pos = Math.min(pos + step, max);
  }
  // does it keep growing if we simply wait at the bottom?
  for (let i = 0; i < 10; i++) {
    await wait(300);
    log.push(`  wait ${(i + 1) * 300}ms -> h=${de.scrollHeight}`);
  }
  return log;
}
"""


def run(width, height, throttle=1):
    profile = os.path.join(WORK, f"p{width}x{height}x{throttle}")
    shutil.rmtree(profile, ignore_errors=True)
    os.makedirs(profile, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            profile, channel="chrome", headless=False,
            viewport={"width": width, "height": height},
            args=["--no-first-run", "--no-default-browser-check"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
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

        print(f"=== viewport {width}x{height} / CPU {throttle}x遅い ===", flush=True)
        if throttle > 1:
            page.context.new_cdp_session(page).send(
                "Emulation.setCPUThrottlingRate", {"rate": throttle})
        print("   検索直後 scrollHeight =",
              page.evaluate("() => document.scrollingElement.scrollHeight"), flush=True)
        # the real order: findScroller() runs on the UN-expanded page
        page.evaluate(BROWSER_JS)
        sc = page.evaluate("() => window.__PATTISHOT__.findScroller()")
        print(f"   findScroller (展開前) = {sc}", flush=True)
        page.evaluate("() => window.__PATTISHOT__.prepare()")
        m = page.evaluate("() => window.__PATTISHOT__.measure()")
        print(f"   prepare後 measure = captureHeight {m['captureHeight']} / "
              f"content {m['contentHeight']} / scrollHeight {m['scrollHeight']} "
              f"/ viewport {m['viewport']}", flush=True)
        if m["captureHeight"] < 20000:
            print("   ★ 途中で切れている -> 内訳を調べる", flush=True)
            for line in page.evaluate(WALK):
                print("      " + line, flush=True)
        page.evaluate("() => window.__PATTISHOT__.restoreAll()")
        ctx.close()


if __name__ == "__main__":
    for w, h, t in ((1920, 950, 4), (1920, 950, 8), (1920, 950, 20)):
        run(w, h, t)
