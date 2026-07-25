"""Desktop-shortcut feature verification.

  1. util.create_desktop_shortcut writes a valid .lnk whose TargetPath is the
     exe (read back via COM), refreshing an existing one without error.
  2. Full UI flow: settings-panel button click -> request attribute -> app-side
     handler -> result attribute -> success toast shown.
"""
import json
import os
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

TMP = os.path.join(tempfile.gettempdir(), "patti_shot_shortcut_test")
DESK = os.path.join(TMP, "desktop")
os.makedirs(DESK, exist_ok=True)
os.environ["PATTI_SHOT_DESKTOP_DIR"] = DESK

from playwright.sync_api import sync_playwright

from patti_shot import browser, util, app
from patti_shot.ui import FLOATING_UI_JS
import fixtures as fx

PROFILE = os.path.join(os.environ["TEMP"], "patti_shot_sc_profile")


def read_target(lnk: str) -> str:
    ps = ("(New-Object -ComObject WScript.Shell).CreateShortcut('"
          + lnk.replace("'", "''") + "').TargetPath")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, text=True, timeout=30)
    return (r.stdout or "").strip()


def main():
    ok = True

    # --- 1: direct creation + refresh ---
    target = os.path.join(TMP, "PATTI_SHOT.exe")
    open(target, "wb").write(b"MZ dummy")
    lnk = util.create_desktop_shortcut(target)
    t1 = read_target(lnk)
    c1 = os.path.exists(lnk) and t1.lower() == target.lower()
    print(f"1 lnk作成: exists={os.path.exists(lnk)} target='{t1}' -> {'PASS' if c1 else 'FAIL'}")
    lnk2 = util.create_desktop_shortcut(target)   # refresh (already exists)
    c1b = lnk2 == lnk and os.path.exists(lnk)
    print(f"1b 再作成(上書き): -> {'PASS' if c1b else 'FAIL'}")
    ok &= c1 and c1b

    # --- 2: UI flow (button -> attr -> app handler -> result -> toast) ---
    os.environ["PATTI_SHOT_FAKE_EXE"] = target
    urls = fx.build_fixtures()
    with sync_playwright() as p:
        lr = browser.launch(p, PROFILE, headless=True, viewport={"width": 1100, "height": 700})
        ctx = lr.context
        ctx.add_init_script('window.__PATTISHOT_SETTINGS__={"fmt":"both","scale":2};'
                            'window.__PATTISHOT_VERSION__="test";')
        ctx.add_init_script(FLOATING_UI_JS)
        page = ctx.new_page()
        page.goto(urls["short"], wait_until="load", timeout=30000)
        page.wait_for_selector("#patti-shot-fab", timeout=10000)
        page.click("#patti-shot-gear")
        page.click("#patti-shot-mkicon")
        # act as the app's polling loop
        req = None
        for _ in range(20):
            req = page.evaluate(app._GET_SHORTCUT)
            if req:
                break
            page.wait_for_timeout(200)
        c2a = bool(req)
        print(f"2a ボタン→要求属性: {req!r} -> {'PASS' if c2a else 'FAIL'}")
        res = app.do_make_shortcut()
        page.evaluate("(r) => document.documentElement.setAttribute("
                      "'data-patti-shot-shortcut-result', r)", json.dumps(res))
        page.wait_for_function(
            "() => { const t=document.getElementById('patti-shot-toast');"
            " return t && t.style.display!=='none' && /ショートカットを作成しました/.test(t.textContent); }",
            timeout=15000)
        toast = page.evaluate("() => document.getElementById('patti-shot-toast').textContent")
        print(f"2b app処理→成功トースト: '{toast}' res={res} -> PASS")
        ctx.close()
    ok &= c2a and res.get("ok") is True

    print("SHORTCUT VERIFICATION:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
