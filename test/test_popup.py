"""Popup smoke test: version shows, update check does not break anything.

The update notice fetches GitHub; whether it shows depends on what is released,
so the assertions are: no console errors, version text matches the manifest,
and the update area is either hidden or contains a working link - never an
error state.
"""
import json
import os
import shutil
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
EXT = os.environ.get("PATTI_SHOT_EXT") or os.path.abspath(os.path.join(HERE, "..", "extension"))
WORK = os.path.join(os.environ["TEMP"], "patti_shot_popup_test")


def main():
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK, exist_ok=True)
    manifest = json.load(open(os.path.join(EXT, "manifest.json"), encoding="utf-8"))
    want = manifest["version"]
    results = {}

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            WORK, channel="msedge", headless=False, no_viewport=True,
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}",
                  "--no-first-run", "--no-default-browser-check"],
            ignore_default_args=["--enable-automation", "--disable-extensions"])
        sw = ctx.service_workers[0] if ctx.service_workers else None
        if not sw:
            # MV3 service workers start lazily - visiting a page wakes them
            warm = ctx.new_page()
            try:
                warm.goto("https://example.com", timeout=30000)
            except Exception:
                pass
            for _ in range(60):
                sw = ctx.service_workers[0] if ctx.service_workers else None
                if sw:
                    break
                time.sleep(0.5)
            warm.close()
        ext_id = sw.url.split("/")[2]

        page = ctx.new_page()
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(f"chrome-extension://{ext_id}/popup.html")
        page.wait_for_timeout(4000)          # update check round-trip

        ver = page.evaluate("() => document.getElementById('ver').textContent")
        upd_display = page.evaluate(
            "() => getComputedStyle(document.getElementById('update')).display")
        upd_text = page.evaluate(
            "() => document.getElementById('update').textContent")

        results["version_shown"] = want in ver
        results["no_console_errors"] = not errors
        results["update_area_sane"] = upd_display == "none" or "新しい版" in upd_text
        print(f"版数表示: {ver} -> {'PASS' if results['version_shown'] else 'FAIL'}", flush=True)
        print(f"コンソールエラー: {len(errors)}件 {errors[:3]} -> "
              f"{'PASS' if results['no_console_errors'] else 'FAIL'}", flush=True)
        print(f"更新通知エリア: display={upd_display} text={upd_text[:60]!r} -> "
              f"{'PASS' if results['update_area_sane'] else 'FAIL'}", flush=True)
        ctx.close()

    ok = all(results.values())
    print("POPUP:", "PASS" if ok else f"FAIL {results}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
