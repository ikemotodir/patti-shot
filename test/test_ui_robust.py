"""UI robustness: the capture control must be reachable however the window is
sized or however the page rebuilds itself.

  1. keyboard shortcut (Ctrl+Shift+S / Alt+S) fires a capture request
  2. a page that wipes the DOM gets the button back (keep-alive re-mount)
  3. tiny window: button stays inside the viewport (never pushed out of reach)
  4. the button still renders on a real site at half-screen width
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from playwright.sync_api import sync_playwright

from patti_shot import browser
from patti_shot.ui import FLOATING_UI_JS
import fixtures as fx

PROFILE = os.path.join(os.environ["TEMP"], "patti_shot_uirobust_profile")
INIT = ('window.__PATTISHOT_SETTINGS__={"fmt":"both","scale":2};'
        'window.__PATTISHOT_VERSION__="test";')

VISIBLE = """() => {
  const f = document.getElementById('patti-shot-fab');
  if (!f) return {ok:false, why:'missing'};
  const r = f.getBoundingClientRect();
  return {ok: r.bottom <= window.innerHeight + 0.5 && r.right <= window.innerWidth + 0.5
              && r.top >= 0 && r.left >= 0 && r.width > 0,
          rect:{t:Math.round(r.top), b:Math.round(r.bottom), r:Math.round(r.right)},
          vw:window.innerWidth, vh:window.innerHeight};
}"""


def main():
    urls = fx.build_fixtures()
    ok = True
    with sync_playwright() as p:
        lr = browser.launch(p, PROFILE, headless=True, viewport={"width": 1100, "height": 700})
        ctx = lr.context
        ctx.add_init_script(INIT)
        ctx.add_init_script(FLOATING_UI_JS)

        # 1: keyboard shortcut
        page = ctx.new_page()
        page.goto(urls["short"], wait_until="load", timeout=30000)
        page.wait_for_selector("#patti-shot-fab", timeout=10000)
        page.keyboard.press("Control+Shift+S")
        page.wait_for_timeout(400)
        req = page.evaluate("() => document.documentElement.getAttribute('data-patti-shot-request')")
        c1 = bool(req)
        print(f"1 ショートカット(Ctrl+Shift+S): req={req!r} -> {'PASS' if c1 else 'FAIL'}")
        page.evaluate("() => document.documentElement.removeAttribute('data-patti-shot-request')")
        page.close()

        # 2: keep-alive re-mount after the page wipes the DOM
        page = ctx.new_page()
        page.goto(urls["short"], wait_until="load", timeout=30000)
        page.wait_for_selector("#patti-shot-fab", timeout=10000)
        page.evaluate("() => { document.body.innerHTML = '<p>rebuilt by the page</p>'; }")
        gone = page.evaluate("() => !document.getElementById('patti-shot-fab')")
        try:
            page.wait_for_selector("#patti-shot-fab", timeout=8000)
            back = True
        except Exception:
            back = False
        c2 = gone and back
        print(f"2 DOM破棄からの自動復帰: 消えた={gone} 復帰={back} -> {'PASS' if c2 else 'FAIL'}")
        page.close()

        # 3: tiny window -> button still fully inside the viewport
        small = ctx.new_page()
        small.set_viewport_size({"width": 420, "height": 380})
        small.goto(urls["short"], wait_until="load", timeout=30000)
        small.wait_for_selector("#patti-shot-fab", timeout=10000)
        small.wait_for_timeout(500)
        v = small.evaluate(VISIBLE)
        c3 = v["ok"]
        print(f"3 極小ウィンドウで画面内: {v} -> {'PASS' if c3 else 'FAIL'}")
        small.close()

        # 4: real site at half-screen width
        real = ctx.new_page()
        real.set_viewport_size({"width": 940, "height": 1040})
        real.goto("https://www.google.com/", wait_until="domcontentloaded", timeout=45000)
        real.wait_for_selector("#patti-shot-fab", timeout=15000)
        real.wait_for_timeout(2000)
        v4 = real.evaluate(VISIBLE)
        c4 = v4["ok"]
        print(f"4 実サイト(半画面幅)で表示: {v4} -> {'PASS' if c4 else 'FAIL'}")
        real.close()

        ctx.close()
    ok = c1 and c2 and c3 and c4
    print("UI ROBUSTNESS:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
