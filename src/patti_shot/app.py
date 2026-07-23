"""PATTI SHOT desktop app (spec sections 2-4).

Opens a persistent Chrome window with the floating UI injected. Clicking the
pink PATTI SHOT button captures the current page (full length), writes PNG/PDF
to Downloads\\PATTI SHOT\\, and opens that folder. Login state persists across
runs via the persistent profile.
"""
from __future__ import annotations

import json
import os
import sys
import threading

from playwright.sync_api import sync_playwright

from . import __version__, browser, engine, output, update, util
from .ui import FLOATING_UI_JS

START_URL = "https://www.google.com/"


def _settings_path() -> str:
    base = os.path.dirname(browser.default_profile_dir())  # ...\PATTI SHOT
    return os.path.join(base, "settings.json")


def load_settings() -> dict:
    try:
        with open(_settings_path(), encoding="utf-8") as f:
            s = json.load(f)
        return {"fmt": s.get("fmt", "both"), "scale": int(s.get("scale", 2))}
    except Exception:
        return {"fmt": "both", "scale": 2}


def save_settings(s: dict) -> None:
    try:
        with open(_settings_path(), "w", encoding="utf-8") as f:
            json.dump({"fmt": s.get("fmt", "both"), "scale": int(s.get("scale", 2))}, f)
    except Exception:
        pass


def do_capture(page, s: dict, channel: str) -> dict:
    fmt = s.get("fmt", "both")
    scale = int(s.get("scale", 2))
    try:
        orig_title = page.title()
    except Exception:
        orig_title = None

    def progress(done, total):
        try:
            page.evaluate("(t) => { document.title = t; }",
                          f"PATTI SHOT 撮影中 {done}/{total}")
        except Exception:
            pass

    try:
        # reuse_buffer keeps the long-running app's memory flat; safe because we
        # save each result before the next capture can reuse the buffer.
        result = engine.capture(page, scale=scale, channel=channel,
                                progress_callback=progress, reuse_buffer=True)
        out_dir = util.default_save_dir()
        base = util.output_basename(page.url)
        files = output.save_outputs(result.array, out_dir, base, result.scale, fmt=fmt)
        del result
        util.release_memory()
        if not os.environ.get("PATTI_SHOT_NO_OPEN"):
            try:
                os.startfile(out_dir)  # noqa: S606 (Windows: open Explorer)
            except Exception:
                pass
        return {"ok": True, "files": [os.path.basename(f) for f in files], "dir": out_dir}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    finally:
        if orig_title is not None:
            try:
                page.evaluate("(t) => { document.title = t; }", orig_title)
            except Exception:
                pass


_GET_REQ = ("() => { const a = document.documentElement.getAttribute('data-patti-shot-request');"
            " if (a) document.documentElement.removeAttribute('data-patti-shot-request'); return a; }")
_GET_SET = ("() => { const a = document.documentElement.getAttribute('data-patti-shot-settings');"
            " if (a) document.documentElement.removeAttribute('data-patti-shot-settings'); return a; }")


def run(headless: bool = False) -> int:
    settings = load_settings()

    # machine-verification mode for the update pipeline (condition 9): check
    # synchronously, apply if newer, exit -- no browser involved. The optional
    # marker file lets the harness see the relaunched exe run (env is inherited
    # through the updater batch into the restarted process).
    if os.environ.get("PATTI_SHOT_UPDATE_TEST"):
        def _mark(msg: str) -> None:
            mp = os.environ.get("PATTI_SHOT_UPDATE_MARKER")
            if mp:
                with open(mp, "a", encoding="utf-8") as f:
                    f.write(msg + "\n")
        info = update.check_latest()
        if info:
            ok = update.apply_update(info)
            _mark(f"current={__version__} found={info['tag']} applied={ok}")
            print(f"UPDATE_TEST: current={__version__} found={info['tag']} "
                  f"applied={ok}", flush=True)
            return 0 if ok else 1
        _mark(f"current={__version__} no-update")
        print(f"UPDATE_TEST: current={__version__} no-update", flush=True)
        return 0

    # normal startup: check in the background; never block or fail startup.
    upd_state = {"info": None, "applying": False}

    def _check():
        upd_state["info"] = update.check_latest()

    threading.Thread(target=_check, daemon=True).start()

    with sync_playwright() as p:
        lr = browser.launch(p, browser.default_profile_dir(), headless=headless, viewport=None)
        ctx = lr.context
        # inject persisted settings, then the floating UI
        ctx.add_init_script("window.__PATTISHOT_SETTINGS__ = " + json.dumps(settings) + ";")
        ctx.add_init_script(FLOATING_UI_JS)

        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        selftest = os.environ.get("PATTI_SHOT_SELFTEST")
        try:
            page.goto(selftest or START_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass

        # self-test: capture the loaded page once and exit (verifies the whole
        # bundled pipeline in the exe). Enabled via PATTI_SHOT_SELFTEST=<url>.
        if selftest:
            page.wait_for_timeout(800)
            res = do_capture(page, settings, lr.channel)
            print("SELFTEST:", json.dumps(res, ensure_ascii=False), flush=True)
            ctx.close()
            return 0 if res.get("ok") else 1

        # Poll each page for a capture request. The capture (many nested
        # Playwright calls) runs here in the main loop, not in a binding handler
        # -- the sync API cannot re-enter a binding for long, page-driving work.
        while True:
            try:
                pages = ctx.pages
                if not pages:
                    break
                for pg in list(pages):
                    try:
                        # announce a pending update to the injected UI
                        if upd_state["info"] and not upd_state["applying"]:
                            pg.evaluate(
                                "(t) => { window.__PATTISHOT_UI_API__ && "
                                "window.__PATTISHOT_UI_API__.showUpdate(t); }",
                                upd_state["info"]["tag"])
                            if pg.evaluate(
                                    "() => { const d=document.documentElement; "
                                    "if (d.getAttribute('data-patti-shot-update')) "
                                    "{ d.removeAttribute('data-patti-shot-update'); return true; } "
                                    "return false; }"):
                                upd_state["applying"] = True
                                if update.apply_update(upd_state["info"]):
                                    return 0  # updater takes over; exit now
                                upd_state["applying"] = False
                                upd_state["info"] = None  # failed; drop silently
                        s = pg.evaluate(_GET_SET)
                        if s:
                            settings = {"fmt": json.loads(s).get("fmt", "both"),
                                        "scale": int(json.loads(s).get("scale", 2))}
                            save_settings(settings)
                        req = pg.evaluate(_GET_REQ)
                        if req:
                            data = json.loads(req)
                            settings = {"fmt": data.get("fmt", "both"), "scale": int(data.get("scale", 2))}
                            save_settings(settings)
                            result = do_capture(pg, settings, lr.channel)
                            result["id"] = data.get("id")
                            pg.evaluate("(r) => document.documentElement.setAttribute('data-patti-shot-result', r)",
                                        json.dumps(result))
                    except Exception:
                        continue  # page navigated or closed mid-poll
                pages[0].wait_for_timeout(250)  # poll interval + event pump
            except Exception:
                break  # browser closed
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
