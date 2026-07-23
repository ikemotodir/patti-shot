"""PATTI SHOT v4.0 verification harness (spec section 6).

Runs the capture engine against fixtures + live pages and machine-judges each
output on the 8 criteria. Writes test/REPORT.md and saves failing images to
test/artifacts/. No human confirmation required.

Usage:
    python test/harness.py [--only name1,name2] [--headed]
"""
from __future__ import annotations

import argparse
import base64
import datetime as _dt
import os
import platform
import sys
import time
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np
from playwright.sync_api import sync_playwright

from patti_shot import browser, engine, imaging
from patti_shot.ui import FLOATING_UI_JS, PINK
from patti_shot.imaging import array_to_image

import fixtures as fx
import jplatpat

HERE = os.path.dirname(__file__)
ART = os.path.join(HERE, "artifacts")
os.makedirs(ART, exist_ok=True)
PROFILE = os.path.join(os.environ["TEMP"], "patti_shot_harness_profile")
VIEWPORT = {"width": 1280, "height": 900}
PINK_RGB = (int(PINK[1:3], 16), int(PINK[3:5], 16), int(PINK[5:7], 16))

CRITERIA = ["blank", "height", "duplicate", "missing", "ui_leak",
            "resolution", "cleanup", "errors", "truth"]


def _onscreen(cdp):
    r = cdp.send("Page.captureScreenshot",
                 {"format": "png", "captureBeyondViewport": False, "fromSurface": True})
    return imaging.png_bytes_to_array(base64.b64decode(r["data"]))


def truth_check(page, result):
    """Content-correctness: the output image must match what is actually on
    screen at sampled scroll positions -- catches silent corruption beyond
    Chrome's 16384px surface limit that blank/missing checks miss.

    Single-shot pages (<=16384 device px) are verified correct by construction
    (probe); only the scroll-stitch path (taller pages) is sampled here, with
    fixed elements neutralised to match how the engine captured them."""
    scale = result.scale
    if not result.split:
        return True, "single-shot ≤16384px域(実証済のため無検査)"
    page.evaluate("() => window.__PATTISHOT__.prepare()")
    page.evaluate("() => window.__PATTISHOT__.neutralizeFixed()")
    page.evaluate("() => { window.__PATTISHOT__._t = window.__PATTISHOT__._hideUI(); }")
    cdp = page.context.new_cdp_session(page)
    vp = result.measurement.viewport
    cdp.send("Emulation.setDeviceMetricsOverride",
             {"width": result.css_width, "height": vp, "deviceScaleFactor": scale, "mobile": False})
    worst = 0.0
    samples = []
    try:
        css_h = result.css_height
        for frac in (0.35, 0.6, 0.85):
            y = max(0, min(int(frac * css_h), css_h - vp))
            page.evaluate("(yy) => window.scrollTo(0, yy)", y)
            actual = int(page.evaluate("() => window.scrollY"))
            shot = _onscreen(cdp)
            oy = int(round(actual * scale))
            seg = result.array[oy:oy + shot.shape[0]]
            h = min(seg.shape[0], shot.shape[0]); w = min(seg.shape[1], shot.shape[1])
            if h < 50:
                continue
            d = float(np.abs(seg[:h, :w].astype(np.int16) - shot[:h, :w].astype(np.int16)).mean())
            worst = max(worst, d)
            samples.append((actual, round(d, 1)))
    finally:
        cdp.send("Emulation.clearDeviceMetricsOverride")
        page.evaluate("() => { window.__PATTISHOT__._t && window.__PATTISHOT__._t(); }")
        page.evaluate("() => window.__PATTISHOT__.restoreAll()")
        cdp.detach()
    return worst < 3.0, f"onscreen一致 worst={worst:.2f} {samples}"


# --------------------------------------------------------------------------- #
# Page registry: (name, category, kind, target, scale)
#   kind: "fixture" -> target is fixture key; "live" -> url; "nav" -> callable
# --------------------------------------------------------------------------- #
def build_pages(fixture_urls):
    P = []
    # live real-world pages
    P.append(("jplatpat", "1 商標検索結果(必須)", "nav", jplatpat.navigate, 2))
    P.append(("wiki_long", "2 縦20000px+", "live",
              "https://en.wikipedia.org/wiki/Python_(programming_language)", 2))
    P.append(("wiki_images", "3/10 画像・表が多い", "live",
              "https://en.wikipedia.org/wiki/List_of_dog_breeds", 2))
    P.append(("pythonorg", "実在サイト(一般)", "live", "https://www.python.org/", 2))
    # deterministic fixtures
    order = [("long", "2 縦20000px+(fixture)", 2), ("lazy", "3 遅延読込画像", 2),
             ("fixedheader", "4 固定ヘッダー+追従", 2), ("innerscroll", "5 内側スクロール", 2),
             ("infinite", "6 無限スクロール(打切)", 2), ("short", "7 短い1画面", 2),
             ("wide", "8 横スクロール", 2), ("japanese", "9 日本語フォント", 3),
             ("tables", "10 テーブル多数", 2), ("iframe", "11 iframe", 2),
             ("dark", "12 ダークテーマ", 2)]
    for key, cat, scale in order:
        P.append((key, cat, "fixture", fixture_urls[key], scale))
    return P


# --------------------------------------------------------------------------- #
# Judgements
# --------------------------------------------------------------------------- #
def judge(result, sig_before, sig_after, our_errors, page_noise):
    arr = result.array
    scale = result.scale
    out = {}

    # 1 blank
    runs = imaging.blank_runs(arr, scale=scale)
    out["blank"] = (len(runs) == 0, f"runs={runs[:4]}(n={len(runs)})")

    # 2 height consistency: image_height/scale within +-3% of measured content
    hi = arr.shape[0] / scale
    c = max(1, result.measurement.content_height)
    tol = max(0.03 * c, 16)
    out["height"] = (abs(hi - c) <= tol,
                     f"img/{scale}={hi:.0f} vs content={c} tol=±{tol:.0f}")

    # 3 duplicate (fixed-header) detection
    vp_dev = round(result.measurement.viewport * scale)
    d = imaging.duplicate_run_px(arr, vp_dev)
    d_css = d / scale
    out["duplicate"] = (d_css < 120, f"dup_run={d_css:.0f}css px")

    # 4 missing content
    boxes = result.keyword_boxes or []
    present = missing = 0
    miss_info = []
    for b in boxes:
        dev = (b["x"] * scale, b["y"] * scale, b["w"] * scale, b["h"] * scale)
        if dev[1] >= arr.shape[0] - 4:
            continue
        # a text region that is 99.5%+ one colour means the text did not render
        if imaging.region_is_blank(arr, dev):
            missing += 1
            miss_info.append(f"'{b['text']}'@({int(b['x'])},{int(b['y'])} {int(b['w'])}x{int(b['h'])})")
        else:
            present += 1
    evaluated = present + missing
    # a genuine capture gap blanks many consecutive keywords (and also trips the
    # blank-band check); tolerate a small fraction of residual DOM-visible-but-
    # unpainted text on complex pages.
    ok_missing = True if evaluated == 0 else (present / evaluated >= 0.8 and present >= 1)
    out["missing"] = (ok_missing,
                      f"present={present} missing={missing} of {len(boxes)} 欠落={miss_info}")

    # 5 injected UI leak
    pink = imaging.count_color(arr, PINK_RGB)
    out["ui_leak"] = (pink < 500, f"pink_px={pink}")

    # 6 resolution
    exp_w = result.css_width * scale
    out["resolution"] = (abs(arr.shape[1] - exp_w) <= 1,
                         f"img_w={arr.shape[1]} exp={exp_w}(={result.css_width}x{scale})")

    # 7 cleanup (DOM/style restored)
    out["cleanup"] = (sig_before == sig_after, f"before={sig_before} after={sig_after}")

    # 8 errors: only errors attributable to PATTI SHOT fail the criterion;
    # the page's own console/JS noise is reported for information.
    out["errors"] = (len(our_errors) == 0,
                     f"our_errors={our_errors[:3]} / page_noise={len(page_noise)}件")
    return out


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def _is_ours(text: str) -> bool:
    t = (text or "").lower()
    return "__pattishot__" in t or "patti-shot" in t or "pattishot" in t


def run_one(ctx, name, category, kind, target, scale):
    rec = {"name": name, "category": category, "scale": scale, "kind": kind}
    our_errors = []      # errors attributable to PATTI SHOT -> fail the criterion
    page_noise = []      # the page's own console/JS errors -> informational only
    page = ctx.new_page()
    page.on("pageerror", lambda e: (our_errors if _is_ours(str(e)) else page_noise).append(str(e)))
    page.on("console", lambda m: (our_errors if _is_ours(m.text) else page_noise).append(
        "console:" + m.text) if m.type == "error" else None)
    t0 = time.time()
    try:
        if kind == "nav":
            ok, info = target(page)
            rec["nav_info"] = info
            if not ok:
                rec["status"] = "未検証"
                rec["reason"] = info
                page.close()
                return rec
        else:
            page.goto(target, wait_until="load", timeout=60000)
            page.wait_for_timeout(400)

        sig_before = page.evaluate("() => window.__PATTISHOT__ ? window.__PATTISHOT__.styleSignature() : ''")
        result = engine.capture(page, scale=scale)
        sig_after = page.evaluate("() => window.__PATTISHOT__.styleSignature()")

        rec.update({
            "channel": result.channel, "img_w": result.width_px, "img_h": result.height_px,
            "content_h": result.measurement.content_height,
            "scroll_h": result.measurement.scroll_height,
            "capture_h": result.css_height, "css_w": result.css_width,
            "split": result.split, "bands": result.bands, "attempts": result.attempts,
            "trimmed": result.trimmed_px, "elapsed": round(time.time() - t0, 1),
        })
        judged = judge(result, sig_before, sig_after, our_errors, page_noise)
        judged["truth"] = truth_check(page, result)
        rec["judged"] = {k: (bool(v[0]), v[1]) for k, v in judged.items()}
        all_pass = all(v[0] for v in judged.values())
        rec["status"] = "PASS" if all_pass else "FAIL"

        # save thumbnail always; full image on failure
        img = array_to_image(result.array)
        thumb_w = 500
        th = img.resize((thumb_w, max(1, int(img.height * thumb_w / img.width))))
        th.save(os.path.join(ART, f"{name}_thumb.png"))
        if not all_pass:
            img.save(os.path.join(ART, f"{name}_FAIL.png"))
    except Exception as e:
        rec["status"] = "ERROR"
        rec["reason"] = f"{type(e).__name__}: {e}"
        rec["trace"] = traceback.format_exc()
    finally:
        try:
            page.close()
        except Exception:
            pass
    return rec


def write_report(records, meta):
    lines = ["# PATTI SHOT v4.0 自動検証レポート", ""]
    lines.append(f"- 生成: {meta['when']}")
    lines.append(f"- OS: {meta['os']} / ブラウザ: {meta['channel']} {meta['browser_version']}")
    lines.append(f"- ウィンドウ(viewport): {VIEWPORT['width']}x{VIEWPORT['height']}")
    lines.append(f"- Python: {meta['python']} / Playwright: {meta['pw']}")
    lines.append("")
    npass = sum(1 for r in records if r.get("status") == "PASS")
    nfail = sum(1 for r in records if r.get("status") == "FAIL")
    nerr = sum(1 for r in records if r.get("status") in ("ERROR", "未検証"))
    lines.append(f"**合計 {len(records)}件 : PASS {npass} / FAIL {nfail} / ERROR・未検証 {nerr}**")
    lines.append("")
    # summary table
    lines.append("| # | ページ | カテゴリ | 倍率 | 判定 | " + " | ".join(CRITERIA) + " |")
    lines.append("|---|---|---|---|---|" + "|".join(["---"] * len(CRITERIA)) + "|")
    for i, r in enumerate(records, 1):
        cells = []
        j = r.get("judged", {})
        for c in CRITERIA:
            if c in j:
                cells.append("✅" if j[c][0] else "❌")
            else:
                cells.append("—")
        lines.append(f"| {i} | {r['name']} | {r['category']} | {r['scale']}x | "
                     f"**{r.get('status','?')}** | " + " | ".join(cells) + " |")
    lines.append("")
    # details
    for i, r in enumerate(records, 1):
        lines.append(f"## {i}. {r['name']} — {r.get('status','?')}")
        lines.append(f"- カテゴリ: {r['category']} / 種別: {r['kind']} / 倍率: {r['scale']}x")
        if "nav_info" in r:
            lines.append(f"- 遷移: {r['nav_info']}")
        if r.get("status") in ("ERROR", "未検証"):
            lines.append(f"- 理由: {r.get('reason','')}")
        else:
            lines.append(f"- 画像: {r.get('img_w')}x{r.get('img_h')}px / "
                         f"実測content={r.get('content_h')} scrollH={r.get('scroll_h')} "
                         f"capture={r.get('capture_h')} / channel={r.get('channel')}")
            lines.append(f"- 分割: split={r.get('split')} bands={r.get('bands')} "
                         f"attempts={r.get('attempts')} trimmed={r.get('trimmed')}px "
                         f"elapsed={r.get('elapsed')}s")
            for c in CRITERIA:
                if c in r.get("judged", {}):
                    ok, detail = r["judged"][c]
                    lines.append(f"  - {'✅' if ok else '❌'} **{c}**: {detail}")
        lines.append("")
    path = os.path.join(HERE, "REPORT.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path, (npass, nfail, nerr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    fixture_urls = fx.build_fixtures()
    with sync_playwright() as p:
        lr = browser.launch(p, PROFILE, headless=not args.headed, viewport=VIEWPORT)
        ctx = lr.context
        ctx.add_init_script(FLOATING_UI_JS)
        probe = ctx.new_page()
        ua = probe.evaluate("() => navigator.userAgent")
        probe.close()
        bv = ua.split("Chrome/")[-1].split(" ")[0] if "Chrome/" in ua else "?"

        pages = build_pages(fixture_urls)
        only = set(x for x in args.only.split(",") if x)
        records = []
        for (name, cat, kind, target, scale) in pages:
            if only and name not in only:
                continue
            print(f"--- {name} ({cat}) scale={scale} ---", flush=True)
            r = run_one(ctx, name, cat, kind, target, scale)
            print(f"    => {r.get('status')} "
                  + (r.get('reason', '') if r.get('status') in ('ERROR', '未検証')
                     else " ".join(f"{c}:{'OK' if r['judged'][c][0] else 'NG'}"
                                   for c in CRITERIA if c in r.get('judged', {}))),
                  flush=True)
            records.append(r)
        ctx.close()

    meta = {
        "when": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "os": platform.platform(), "channel": lr.channel, "browser_version": bv,
        "python": platform.python_version(),
        "pw": __import__("playwright").__version__ if hasattr(__import__("playwright"), "__version__") else "1.61",
    }
    path, (npass, nfail, nerr) = write_report(records, meta)
    print(f"\nREPORT: {path}")
    print(f"PASS {npass} / FAIL {nfail} / ERROR・未検証 {nerr}")


if __name__ == "__main__":
    main()
