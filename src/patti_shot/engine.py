"""Capture orchestration (spec section 4: STEP1-3).

prepare -> measure -> CDP clip capture (single or auto-split) -> stitch ->
blank auto-detect + retry -> trailing trim -> full DOM/style restore.
"""
from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
from playwright.sync_api import Page

_DEBUG = bool(os.environ.get("PATTI_DEBUG"))


def _dbg(msg: str) -> None:
    if _DEBUG:
        print(f"   [engine] {msg}", flush=True)

from . import imaging
from .jslib import BROWSER_JS

# A single captureBeyondViewport renders the whole page once, so one shot is
# far faster than N bands. We default to one shot bounded only by a memory
# budget, and fall back to splitting (STEP3 "区間分割撮影") only when a blank is
# actually detected -- self-correcting for pages past Chrome's raster limit.
PIXEL_BUDGET = 220_000_000          # max pixels per shot (~660 MB @ 3 channels)
# captureBeyondViewport silently renders WRONG content beyond Chrome's ~16384px
# surface limit (verified: pixel-correct at y=15000, corrupt at y=16500 vs the
# actual on-screen pixels -- and it is not blank, so blank checks miss it). So a
# single shot is only trusted below this device height; taller pages use scroll-
# stitch (each viewport screenshotted on-screen, always < the limit).
SINGLE_SHOT_MAX_DEVICE = 16000


@dataclass
class Measurement:
    content_height: int
    scroll_height: int
    width: int
    capture_height: int
    viewport: int


@dataclass
class CaptureResult:
    array: np.ndarray            # (H, W, 3) uint8 stitched image
    scale: int
    css_width: int               # effective viewport width used (device-independent)
    css_height: int              # capture height in css px
    measurement: Measurement
    bands: int
    attempts: int
    split: bool
    trimmed_px: int
    blank_runs: List = field(default_factory=list)
    channel: str = ""
    keyword_boxes: List = field(default_factory=list)  # css-px {text,x,y,w,h}

    @property
    def height_px(self) -> int:
        return self.array.shape[0]

    @property
    def width_px(self) -> int:
        return self.array.shape[1]


_CDP_CACHE: dict = {}
# One reused output buffer (grow-only) for the long-running app: allocating a
# fresh multi-hundred-MB array every capture fragments against Playwright's own
# allocations and the freed pages are never reused -> memory grows each capture.
# Reusing one buffer keeps it flat. Only safe when the caller consumes each
# result before the next capture (the app does; tests keep multiple results so
# they leave reuse_buffer=False and get independent arrays).
_OUT_BUF: dict = {"a": None}


def _reused_out(h: int, w: int) -> np.ndarray:
    b = _OUT_BUF["a"]
    if b is None or b.shape[0] < h or b.shape[1] < w:
        _OUT_BUF["a"] = b = np.empty((max(h, 1), max(w, 1), 3), dtype=np.uint8)
    return b[:h, :w]


def _cdp_for(page: Page):
    """One reused CDP session per page (creating one per capture accumulates
    session objects and their buffers)."""
    key = id(page)
    cdp = _CDP_CACHE.get(key)
    if cdp is None:
        cdp = page.context.new_cdp_session(page)
        _CDP_CACHE[key] = cdp
    return cdp


def _ensure_api(page: Page) -> None:
    page.evaluate(BROWSER_JS)


def _capture_band(cdp, x: int, y: int, w: int, h: int, scale: float) -> np.ndarray:
    """Single shot from y=0 (captureBeyondViewport tiles downward reliably)."""
    res = cdp.send("Page.captureScreenshot", {
        "format": "png",
        "captureBeyondViewport": True,
        "fromSurface": True,
        "clip": {"x": float(x), "y": float(y), "width": float(w),
                 "height": float(h), "scale": float(scale)},
    })
    return imaging.png_bytes_to_array(base64.b64decode(res["data"]))


def _capture_viewport_noclip(cdp) -> np.ndarray:
    """Screenshot the currently visible viewport with no clip (so there is no
    high-offset clip to hit Chrome's surface limit). The device-scale factor is
    set via Emulation by the caller, so the image is already at target scale."""
    res = cdp.send("Page.captureScreenshot", {
        "format": "png", "captureBeyondViewport": False, "fromSurface": True,
    })
    return imaging.png_bytes_to_array(base64.b64decode(res["data"]))


def capture(page: Page, scale: int = 2, retries: int = 3,
            hide_ui: bool = True, channel: str = "",
            force_band_css: Optional[int] = None,
            progress_callback=None, reuse_buffer: bool = False) -> CaptureResult:
    def _progress(done, total):
        if progress_callback:
            try:
                progress_callback(done, total)
            except Exception:
                pass
    _ensure_api(page)

    # STEP1: prepare (scroller, lazy-load, forced render). STEP2: measure.
    t = time.time()
    page.evaluate("() => window.__PATTISHOT__.prepare()")
    _dbg(f"prepare {time.time()-t:.1f}s")
    t = time.time()
    m = page.evaluate("() => window.__PATTISHOT__.measure()")
    _dbg(f"measure {time.time()-t:.1f}s -> {m}")
    meas = Measurement(m["contentHeight"], m["scrollHeight"], m["width"],
                       m["captureHeight"], m["viewport"])

    # widen viewport if the page has horizontal content, so image width is an
    # exact (viewport x scale) multiple (spec section 6 resolution rule).
    orig_vp = page.viewport_size
    if orig_vp and meas.width > orig_vp["width"]:
        page.set_viewport_size({"width": int(meas.width), "height": orig_vp["height"]})
        page.evaluate("() => window.__PATTISHOT__.prepare()")
        m = page.evaluate("() => window.__PATTISHOT__.measure()")
        meas = Measurement(m["contentHeight"], m["scrollHeight"], m["width"],
                           m["captureHeight"], m["viewport"])
    css_width = int(page.evaluate("() => window.innerWidth"))
    css_height = int(meas.capture_height)

    # hide our own injected UI so it never appears in the capture
    if hide_ui:
        page.evaluate("() => { window.__PATTISHOT__._hideRestore = "
                      "window.__PATTISHOT__._hideUI(); }")

    def needs_split(scale_: int) -> bool:
        if force_band_css or reuse_buffer:
            return True  # scroll-stitch: small band decodes into a reused buffer
        if css_height * scale_ > SINGLE_SHOT_MAX_DEVICE:
            return True
        if css_width * css_height * scale_ * scale_ > PIXEL_BUDGET:
            return True
        return False

    cdp = _cdp_for(page)
    cur_scale = scale
    attempts = 0
    result_arr = None
    bands_used = 1
    split = False
    trimmed = 0
    runs: List = []
    keyword_boxes: List = []
    neutralised = False

    try:
        while attempts < max(1, retries):
            attempts += 1
            split = needs_split(cur_scale)
            tcap = time.time()
            if not split:
                # single shot from the top -- fast and seamless
                _progress(0, 1)
                arr = _capture_band(cdp, 0, 0, css_width, css_height, cur_scale)
                _progress(1, 1)
                bands_used = 1
            else:
                # region-split via scrolling (STEP3 "区間分割撮影"). Neutralise
                # fixed/sticky so scrolling duplicates nothing, set the device
                # scale via Emulation, then screenshot each scrolled viewport
                # (no clip -> no high-offset render limit) into ONE pre-allocated
                # buffer. A fixed-size buffer (reused each capture) + freeing each
                # band avoids numpy caching many varied-size band buffers (leak).
                if not neutralised:
                    page.evaluate("() => window.__PATTISHOT__.neutralizeFixed()")
                    neutralised = True
                vp = meas.viewport
                cdp.send("Emulation.setDeviceMetricsOverride", {
                    "width": css_width, "height": vp,
                    "deviceScaleFactor": cur_scale, "mobile": False})
                total_dev = int(round(css_height * cur_scale))
                out = (_reused_out(total_dev, css_width * cur_scale) if reuse_buffer
                       else np.empty((total_dev, css_width * cur_scale, 3), dtype=np.uint8))
                est_total = max(1, -(-total_dev // int(vp * cur_scale)))
                covered = 0
                bands_used = 0
                try:
                    guard = 0
                    while covered < total_dev and guard < 100000:
                        guard += 1
                        _progress(bands_used, est_total)
                        covered_css = covered / cur_scale
                        page.evaluate("(y) => window.scrollTo(0, y)", covered_css)
                        actual = float(page.evaluate("() => window.scrollY"))
                        img = _capture_viewport_noclip(cdp)
                        top_crop = max(0, covered - int(round(actual * cur_scale)))
                        avail = img.shape[0] - top_crop
                        take = min(avail, total_dev - covered)
                        if take <= 0:
                            break
                        w = min(out.shape[1], img.shape[1])
                        out[covered:covered + take, :w] = img[top_crop:top_crop + take, :w]
                        covered += take
                        bands_used += 1
                        del img
                finally:
                    cdp.send("Emulation.clearDeviceMetricsOverride")
                    # our raw CDP override can drop Playwright's viewport
                    # emulation; force it to re-establish so later captures are
                    # unaffected (Playwright's own viewport_size won't notice).
                    if orig_vp:
                        page.set_viewport_size({"width": orig_vp["width"],
                                                "height": orig_vp["height"] + 1})
                        page.set_viewport_size(orig_vp)
                    page.evaluate("() => window.scrollTo(0, 0)")
                arr = out[:covered]
            _dbg(f"attempt{attempts} scale={cur_scale} split={split} bands={bands_used} "
                 f"capture {time.time()-tcap:.1f}s")

            # trailing trim: never cut measured content
            max_trim = max(0, int((css_height - meas.content_height) * cur_scale) + 4 * cur_scale)
            arr, trimmed = imaging.trim_trailing_uniform(arr, max_trim=max_trim)

            runs = imaging.blank_runs(arr, ignore_bottom_px=0, scale=cur_scale)
            result_arr = arr
            if not runs:
                break
            # auto-retry (spec STEP3): drop resolution (fewer device px) and
            # retry -- covers pages past the single-shot limit.
            if cur_scale > 1:
                cur_scale -= 1
            else:
                break  # exhausted; keep best-effort result and report the runs

        # keyword boxes for the missing-content check, taken while the page is
        # still in its prepared (expanded) layout, before restore.
        keyword_boxes = page.evaluate(
            "(h) => window.__PATTISHOT__.keywordBoxes(12, h)", meas.content_height)
    finally:
        if hide_ui:
            page.evaluate("() => { window.__PATTISHOT__._hideRestore && "
                          "window.__PATTISHOT__._hideRestore(); }")
        if orig_vp and page.viewport_size and page.viewport_size != orig_vp:
            page.set_viewport_size(orig_vp)
        page.evaluate("() => window.__PATTISHOT__.restoreAll()")
        # cdp session is cached and reused; not detached here

    return CaptureResult(
        array=result_arr, scale=cur_scale, css_width=css_width, css_height=css_height,
        measurement=meas, bands=bands_used, attempts=attempts, split=split,
        trimmed_px=trimmed, blank_runs=runs, channel=channel,
        keyword_boxes=keyword_boxes,
    )
