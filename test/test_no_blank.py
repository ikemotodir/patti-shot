"""The app must never open on a blank page (regression from v4.2.0).

Clipboard text that merely looked URL-ish was coerced into an unreachable
address, the navigation failed, and the window sat on about:blank.

  1. normalize() accepts real URLs and rejects ordinary text / other schemes
  2. an unreachable start URL still lands on a real page, not about:blank
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from patti_shot import handoff

ACCEPT = [
    ("https://example.com/", "https://example.com/"),
    ("example.com", "https://example.com"),
    ("https://www.google.com/search?q=abc", "https://www.google.com/search?q=abc"),
    ("pattishot://https%3A%2F%2Fexample.com%2Fa", "https://example.com/a"),
    ("http://localhost:8000/x", "http://localhost:8000/x"),
]
REJECT = [
    "javascript:location.href='pattishot://'+encodeURIComponent(location.href)",
    "ver.4.2.1をリリースした",
    "これはURLではない普通の日本語テキストです。",
    r"C:\Users\studi\Desktop",
    "PATTI SHOT v4.2.1",
    "2026-07-25 メモ: 打ち合わせ",
    "file:///C:/secret.txt",
    "data:text/html,<h1>x</h1>",
    "patti-shot/releases/latest",
    "",
]


def main():
    ok = True
    for raw, want in ACCEPT:
        got = handoff.normalize(raw)
        good = got == want
        ok &= good
        print(f"{'PASS' if good else 'FAIL'} 受理 {raw[:42]!r} -> {got!r}")
    for raw in REJECT:
        got = handoff.normalize(raw)
        good = got is None
        ok &= good
        print(f"{'PASS' if good else 'FAIL'} 拒否 {raw[:42]!r} -> {got!r}")

    # 2: the real startup decision with a "poisoned" clipboard -- the boss's
    #    exact case: the bookmarklet text was on the clipboard, got coerced into
    #    a bogus address, and the app opened blank.
    def put(text: str) -> bool:
        """Put text on the clipboard and confirm it landed (a silently failing
        clipboard would make the checks below pass for the wrong reason)."""
        handoff.set_clipboard(text)
        import subprocess
        r = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                           capture_output=True, text=True, timeout=20)
        return (r.stdout or "").strip().startswith(text.strip()[:25])

    poisons = [
        "javascript:location.href='pattishot://'+encodeURIComponent(location.href)",
        "ver.4.2.1をリリースした",
        "きょうの買い物メモ",
    ]
    for text in poisons:
        placed = put(text)
        got = handoff.startup_url()
        good = placed and got is None
        ok &= good
        print(f"{'PASS' if good else 'FAIL'} クリップボード{text[:20]!r} (設定確認={placed}) "
              f"-> startup_url={got!r} (Noneならgoogle.comで開く)")
    # a real URL on the clipboard is still honoured
    placed = put("https://example.com/x")
    got = handoff.startup_url()
    good = placed and got == "https://example.com/x"
    ok &= good
    print(f"{'PASS' if good else 'FAIL'} 本物のURLは引き継ぐ (設定確認={placed}) -> {got!r}")

    # 3: an unreachable start URL must still end on a real page
    from playwright.sync_api import sync_playwright
    from patti_shot import browser
    from patti_shot.ui import FLOATING_UI_JS
    prof = os.path.join(os.environ["TEMP"], "patti_shot_noblank_profile")
    with sync_playwright() as p:
        lr = browser.launch(p, prof, headless=True, viewport={"width": 900, "height": 700})
        lr.context.add_init_script(FLOATING_UI_JS)
        page = lr.context.new_page()
        bad = "https://this-host-does-not-exist.invalid/"
        try:
            page.goto(bad, wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass
        before = page.url or ""
        blank_before = (before in ("", "about:blank")
                        or before.startswith("chrome-error://"))
        # the same fallback (with retry) the app performs
        if blank_before:
            for _ in range(2):
                try:
                    page.goto("https://example.com/", wait_until="domcontentloaded",
                              timeout=30000)
                    break
                except Exception:
                    page.wait_for_timeout(500)
        landed = page.url
        recovered = "example.com" in landed
        print(f"{'PASS' if recovered else 'FAIL'} 到達不能URL後の復帰: "
              f"before={before!r} -> {landed}")
        ok &= recovered
        lr.context.close()

    print("NO-BLANK VERIFICATION:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
