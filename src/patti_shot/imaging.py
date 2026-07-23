"""Image analysis and assembly for PATTI SHOT.

Pure functions used by both the capture engine (blank auto-detection,
trailing trim, stitching) and the verification harness (blank / duplicate /
keyword-presence judgements). No Playwright dependency here.
"""
from __future__ import annotations

import io
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None  # allow very tall stitched images

BAND_PX = 100          # height of a scan band (device px), per spec section 6
BLANK_RATIO = 0.995    # a band is "blank" when one colour covers >= 99.5%
BLANK_RUN_PX = 300     # blank run >= 300px continuous => FAIL


# --------------------------------------------------------------------------- #
# Conversions
# --------------------------------------------------------------------------- #
def png_bytes_to_array(data: bytes) -> np.ndarray:
    """Decode PNG bytes to an RGB uint8 array (H, W, 3).

    Uses np.array (a copy) and closes the PIL image so the decoder's buffers are
    released immediately -- np.asarray would keep a view onto the PIL image and
    leak one image's worth of memory per capture.
    """
    with Image.open(io.BytesIO(data)) as im:
        im.load()
        a = np.asarray(im)  # view onto PIL's buffer
        if a.ndim == 2:
            a = a[:, :, None].repeat(3, axis=2)
        rgb = a[:, :, :3]
        # Copy the pixels into a numpy-OWNED buffer. A view onto the PIL image
        # would keep its decoder buffer alive (the allocator never returns it ->
        # ~one image leaked per capture). A fresh same-size np.empty is reused by
        # numpy across captures, so memory stays flat.
        out = np.empty((rgb.shape[0], rgb.shape[1], 3), dtype=np.uint8)
        out[...] = rgb
        return out


def array_to_image(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(arr, "RGB")


def stitch_vertical(arrays: List[np.ndarray]) -> np.ndarray:
    """Stack same-width band arrays into one tall array."""
    if not arrays:
        raise ValueError("no arrays to stitch")
    if len(arrays) == 1:
        return arrays[0]  # single shot: no copy needed
    width = max(a.shape[1] for a in arrays)
    fixed = []
    for a in arrays:
        if a.shape[1] != width:
            # pad narrower bands on the right with their edge colour
            pad = np.repeat(a[:, -1:, :], width - a.shape[1], axis=1)
            a = np.concatenate([a, pad], axis=1)
        fixed.append(a)
    return np.concatenate(fixed, axis=0)


# --------------------------------------------------------------------------- #
# Blank detection & trailing trim
# --------------------------------------------------------------------------- #
def _band_is_blank(band: np.ndarray) -> bool:
    """True when a single colour occupies >= BLANK_RATIO of the band."""
    flat = band.reshape(-1, band.shape[2])
    if flat.shape[0] == 0:
        return True
    # pack RGB into one int; np.unique (a sort) avoids bincount allocating a
    # 16M-entry table per band on tall images.
    packed = ((flat[:, 0].astype(np.uint32) << 16)
              | (flat[:, 1].astype(np.uint32) << 8) | flat[:, 2].astype(np.uint32))
    _, counts = np.unique(packed, return_counts=True)
    return counts.max() / packed.size >= BLANK_RATIO


def blank_runs(arr: np.ndarray, ignore_bottom_px: int = 0,
               scale: float = 1.0) -> List[Tuple[int, int]]:
    """Return [(y_start, y_end), ...] device-px ranges of continuous blank
    bands. A run must be >= BLANK_RUN_PX *CSS* px (i.e. BLANK_RUN_PX * scale
    device px) so the threshold is resolution-invariant. The bottom
    ``ignore_bottom_px`` rows are excluded (intentional trailing margin)."""
    run_threshold = BLANK_RUN_PX * scale
    h = arr.shape[0]
    limit = max(0, h - ignore_bottom_px)
    flags = []
    ys = list(range(0, limit, BAND_PX))
    for y in ys:
        band = arr[y:min(y + BAND_PX, limit)]
        if band.shape[0] == 0:
            continue
        flags.append((y, min(y + BAND_PX, limit), _band_is_blank(band)))

    runs: List[Tuple[int, int]] = []
    run_start: Optional[int] = None
    run_end = 0
    for y0, y1, blank in flags:
        if blank:
            if run_start is None:
                run_start = y0
            run_end = y1
        else:
            if run_start is not None and run_end - run_start >= run_threshold:
                runs.append((run_start, run_end))
            run_start = None
    if run_start is not None and run_end - run_start >= run_threshold:
        runs.append((run_start, run_end))
    return runs


def _uniform_rows_from_bottom(arr: np.ndarray) -> int:
    """Count contiguous uniform (single-colour) rows at the bottom."""
    h = arr.shape[0]
    n = 0
    for y in range(h - 1, -1, -1):
        row = arr[y]
        if np.all(row == row[0]):
            n += 1
        else:
            break
    return n


def count_color(arr: np.ndarray, rgb: Tuple[int, int, int]) -> int:
    """Number of pixels exactly matching ``rgb`` (used for injected-UI leak)."""
    r, g, b = rgb
    return int(np.count_nonzero((arr[:, :, 0] == r) & (arr[:, :, 1] == g) & (arr[:, :, 2] == b)))


def trim_trailing_uniform(arr: np.ndarray, keep_margin: int = 8,
                          max_trim: Optional[int] = None) -> Tuple[np.ndarray, int]:
    """Trim the trailing uniform-colour band (measurement-overrun insurance).

    Leaves ``keep_margin`` px of the background. Never trims more than
    ``max_trim`` px (engine passes capture_height - content_height so real
    content is never cut). Returns (trimmed_arr, trimmed_px)."""
    uniform = _uniform_rows_from_bottom(arr)
    trim = max(0, uniform - keep_margin)
    if max_trim is not None:
        trim = min(trim, max_trim)
    if trim <= 0:
        return arr, 0
    return arr[: arr.shape[0] - trim], trim


# --------------------------------------------------------------------------- #
# Duplicate (fixed-header) detection
# --------------------------------------------------------------------------- #
def _row_hashes(arr: np.ndarray) -> np.ndarray:
    # FNV-ish per-row hash over bytes, vectorised via numpy's own hashing proxy
    # (use a cheap but collision-safe reduction)
    flat = arr.reshape(arr.shape[0], -1).astype(np.uint64)
    # weighted sum with two different primes to reduce collisions
    idx = np.arange(flat.shape[1], dtype=np.uint64)
    h1 = (flat * (idx * np.uint64(2654435761) + np.uint64(1))).sum(axis=1)
    return h1


def _uniform_row_mask(arr: np.ndarray) -> np.ndarray:
    first = arr[:, :1, :]
    return np.all(arr == first, axis=(1, 2))


def duplicate_run_px(arr: np.ndarray, viewport_device_px: int) -> int:
    """Longest continuous run (device px) of *content* rows that repeat exactly
    one viewport-height later. Long runs signal fixed-header duplication."""
    offset = int(viewport_device_px)
    if offset <= 0 or arr.shape[0] <= offset:
        return 0
    # downsample columns to bound memory/time on very tall images; duplicated
    # header bands remain detectable at reduced width.
    step = max(1, arr.shape[1] // 256)
    small = arr[:, ::step, :]
    hashes = _row_hashes(small)
    uniform = _uniform_row_mask(small)
    n = arr.shape[0] - offset
    match = (hashes[:n] == hashes[offset:offset + n]) & (~uniform[:n]) & (~uniform[offset:offset + n])
    best = cur = 0
    for m in match:
        if m:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


# --------------------------------------------------------------------------- #
# Keyword-presence (missing-content) check
# --------------------------------------------------------------------------- #
def region_has_content(arr: np.ndarray, box: Tuple[int, int, int, int],
                       std_threshold: float = 6.0) -> bool:
    """box = (x, y, w, h) in device px. True when the region shows real
    variation (not a blank patch)."""
    x, y, w, h = box
    x0, y0 = max(0, int(x)), max(0, int(y))
    x1 = min(arr.shape[1], int(x + w))
    y1 = min(arr.shape[0], int(y + h))
    if x1 <= x0 or y1 <= y0:
        return False
    patch = arr[y0:y1, x0:x1]
    return float(patch.astype(np.float32).std()) > std_threshold


def region_is_blank(arr: np.ndarray, box: Tuple[int, int, int, int]) -> bool:
    x, y, w, h = box
    x0, y0 = max(0, int(x)), max(0, int(y))
    x1 = min(arr.shape[1], int(x + w))
    y1 = min(arr.shape[0], int(y + h))
    if x1 <= x0 or y1 <= y0:
        return True
    patch = arr[y0:y1, x0:x1]
    return _band_is_blank(patch)
