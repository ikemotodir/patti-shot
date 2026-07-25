"""Handoff verification: open the page the user is already looking at.

  1. URL normalisation (plain URL / pattishot:// / percent-encoded / junk)
  2. command-line pickup
  3. single-instance guard + URL handed to the running instance
  4. protocol registration writes the HKCU keys pointing at this exe
  5. the settings-panel button drives the app-side handler (UI flow)
"""
import json
import os
import sys
import winreg

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from playwright.sync_api import sync_playwright

from patti_shot import browser, handoff, app
from patti_shot.ui import FLOATING_UI_JS
import fixtures as fx

PROFILE = os.path.join(os.environ["TEMP"], "patti_shot_handoff_profile")


def main():
    ok = True

    # --- 1: normalisation ---
    cases = [
        ("https://example.com/a?b=1", "https://example.com/a?b=1"),
        ("pattishot://https%3A%2F%2Fexample.com%2Fx", "https://example.com/x"),
        ("pattishot://https://example.com/y", "https://example.com/y"),
        ("  https://example.com/z  ", "https://example.com/z"),
        ("not a url", None),
        ("", None),
    ]
    bad = [(raw, handoff.normalize(raw)) for raw, want in cases
           if handoff.normalize(raw) != want]
    c1 = not bad
    print(f"1 URL正規化: {len(cases)}件 誤り={bad} -> {'PASS' if c1 else 'FAIL'}")

    # --- 2: argv pickup ---
    c2 = (handoff.url_from_argv(["pattishot://https%3A%2F%2Fexample.com%2Fq"])
          == "https://example.com/q") and handoff.url_from_argv(["--flag"]) is None
    print(f"2 コマンドライン取得: -> {'PASS' if c2 else 'FAIL'}")

    # --- 3: single instance + handoff file ---
    first = handoff.claim_single_instance()      # this process claims it
    second = handoff.claim_single_instance()     # same process: already held
    url = "https://example.com/handoff"
    sent = handoff.send_to_running(url)
    got = handoff.take_handoff()
    again = handoff.take_handoff()               # consumed exactly once
    c3 = first and (second is False) and sent and got == url and again is None
    print(f"3 単一起動+受け渡し: first={first} second={second} got={got!r} "
          f"再取得={again} -> {'PASS' if c3 else 'FAIL'}")

    # --- 4: protocol registration ---
    exe = os.path.join(os.environ["TEMP"], "patti_shot_fake.exe")
    open(exe, "wb").write(b"MZ")
    handoff.register_protocol(exe)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                        r"Software\Classes\pattishot\shell\open\command") as k:
        cmd = winreg.QueryValueEx(k, None)[0]
    c4 = exe.lower() in cmd.lower() and "%1" in cmd
    print(f"4 pattishot:登録: command={cmd!r} -> {'PASS' if c4 else 'FAIL'}")

    # --- 5: UI button -> app handler ---
    os.environ["PATTI_SHOT_FAKE_EXE"] = exe
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
        page.click("#patti-shot-oneclick")
        req = None
        for _ in range(20):
            req = page.evaluate(app._GET_ONECLICK)
            if req:
                break
            page.wait_for_timeout(200)
        res = app.do_setup_oneclick()
        page.evaluate("(r) => document.documentElement.setAttribute("
                      "'data-patti-shot-oneclick-result', r)", json.dumps(res))
        page.wait_for_function(
            "() => { const t=document.getElementById('patti-shot-toast');"
            " return t && t.style.display!=='none' && /準備できました/.test(t.textContent); }",
            timeout=15000)
        c5 = bool(req) and res.get("ok") is True
        print(f"5 UIボタン→設定完了トースト: req={req!r} res_ok={res.get('ok')} "
              f"-> {'PASS' if c5 else 'FAIL'}")
        ctx.close()

    ok = c1 and c2 and c3 and c4 and c5
    print("HANDOFF VERIFICATION:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
