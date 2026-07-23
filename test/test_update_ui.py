"""UI-side verification for auto-update (検証指示書 section 3, items 1 & 5).

Headless harness over the exact injected UI shipped in the exe:
  1  showUpdate(tag) -> the pink pill appears with the new version
  5  settings panel shows the running version
  +  click on the pill -> data-patti-shot-update attribute is set (app trigger)
  +  notify(err, true) -> Japanese failure toast with manual-download hint
  +  resetUpdate() -> pill hidden again (post-failure state)
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from playwright.sync_api import sync_playwright

from patti_shot import browser, __version__
from patti_shot.ui import FLOATING_UI_JS
import fixtures as fx

PROFILE = os.path.join(os.environ["TEMP"], "patti_shot_updui_profile")


def main():
    urls = fx.build_fixtures()
    ok = True
    with sync_playwright() as p:
        lr = browser.launch(p, PROFILE, headless=True, viewport={"width": 1100, "height": 700})
        ctx = lr.context
        ctx.add_init_script('window.__PATTISHOT_SETTINGS__={"fmt":"both","scale":2};'
                            f'window.__PATTISHOT_VERSION__={__version__!r};')
        ctx.add_init_script(FLOATING_UI_JS)
        page = ctx.new_page()
        page.goto(urls["short"], wait_until="load", timeout=30000)
        page.wait_for_selector("#patti-shot-fab", timeout=10000)

        # 5: version display in the settings panel
        page.click("#patti-shot-gear")
        ver_txt = page.evaluate("() => document.getElementById('patti-shot-ver').textContent")
        c5 = f"v{__version__}" in ver_txt
        print(f"5 バージョン表示: panel='{ver_txt.strip()}' -> {'PASS' if c5 else 'FAIL'}")
        page.click("#patti-shot-gear")

        # 1: update pill appears
        page.evaluate("() => window.__PATTISHOT_UI_API__.showUpdate('v9.9.9')")
        vis = page.evaluate("() => { const u=document.getElementById('patti-shot-update');"
                            " return u.style.display !== 'none' ? u.textContent : ''; }")
        c1 = "v9.9.9" in vis and "更新" in vis
        print(f"1 更新の検知表示: pill='{vis}' -> {'PASS' if c1 else 'FAIL'}")

        # click -> app trigger attribute
        page.click("#patti-shot-update")
        attr = page.evaluate("() => document.documentElement.getAttribute('data-patti-shot-update')")
        c_click = attr == "1"
        print(f"+ 更新クリック→トリガ属性: {attr!r} -> {'PASS' if c_click else 'FAIL'}")

        # failure toast (Japanese + manual hint) & reset
        page.evaluate("() => window.__PATTISHOT_UI_API__.notify("
                      "'自動更新に失敗しました。\\nお手数ですが配布ページ"
                      "（https://ikemotodir.github.io/patti-shot/）から最新版を"
                      "ダウンロードしてください。', true)")
        toast = page.evaluate("() => { const t=document.getElementById('patti-shot-toast');"
                              " return t.style.display !== 'none' ? t.textContent : ''; }")
        c_toast = "失敗" in toast and "配布ページ" in toast
        print(f"+ 失敗トースト(日本語+逃げ道): shown={bool(toast)} -> {'PASS' if c_toast else 'FAIL'}")

        page.evaluate("() => window.__PATTISHOT_UI_API__.resetUpdate()")
        hidden = page.evaluate("() => document.getElementById('patti-shot-update').style.display === 'none'")
        print(f"+ resetUpdate: hidden={hidden} -> {'PASS' if hidden else 'FAIL'}")

        ctx.close()
        ok = c5 and c1 and c_click and c_toast and hidden
    print("UPDATE UI VERIFICATION:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
