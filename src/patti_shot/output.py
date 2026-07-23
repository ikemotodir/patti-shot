"""PNG / PDF output (spec section 4 STEP4).

PNG: direct save, with a split-into-multiple-files fallback for enormous
images. PDF: lossless (readable text) via img2pdf, auto-split into multiple
pages when the 14,400pt page-size limit is exceeded, cutting at whitespace rows
so text lines are never sliced.
"""
from __future__ import annotations

import io
import os
from typing import List

import img2pdf
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

# PDF page limit is 14,400pt (200in). css px -> pt is *72/96 = *0.75, so a page
# of <= 19,000 css px stays under the limit with margin.
PDF_PAGE_MAX_CSS = 19000
# Last-resort PNG split height (only used when a single file cannot be written).
PNG_SPLIT_HEIGHT = 30000


def _uniform_row(arr: np.ndarray, y: int) -> bool:
    row = arr[y]
    return bool(np.all(row == row[0]))


def find_split_row(arr: np.ndarray, target: int, search: int) -> int:
    """Find a whitespace (uniform) row at or just above ``target`` so a page
    break never cuts through a line of text."""
    lo = max(1, target - search)
    for y in range(min(target, arr.shape[0] - 1), lo, -1):
        if _uniform_row(arr, y):
            return y
    return target


def save_png(arr: np.ndarray, base_path: str) -> List[str]:
    """Save ``arr`` as a single PNG. Fallback chain (spec STEP4): single file ->
    progressively lower resolution -> split into numbered files. Returns the
    written paths (one unless the split fallback was needed)."""
    path = base_path + ".png"
    # 1. single file at full resolution
    try:
        Image.fromarray(arr, "RGB").save(path, "PNG", optimize=False)
        return [path]
    except (MemoryError, OSError, ValueError):
        pass
    # 2. progressively downscale and try a single file
    for factor in (0.75, 0.5):
        try:
            im = Image.fromarray(arr, "RGB")
            im = im.resize((max(1, int(im.width * factor)), max(1, int(im.height * factor))))
            im.save(path, "PNG", optimize=False)
            return [path]
        except (MemoryError, OSError, ValueError):
            continue
    # 3. last resort: split into numbered files
    written = []
    h = arr.shape[0]
    n = -(-h // PNG_SPLIT_HEIGHT)  # ceil
    for i in range(n):
        y0 = i * PNG_SPLIT_HEIGHT
        y1 = min(h, y0 + PNG_SPLIT_HEIGHT)
        p = f"{base_path}_{i + 1}.png"
        Image.fromarray(arr[y0:y1], "RGB").save(p, "PNG", optimize=False)
        written.append(p)
    return written


def save_pdf(arr: np.ndarray, base_path: str, scale: int) -> str:
    """Save ``arr`` as a single lossless PDF, auto-split into multiple pages at
    line-safe boundaries when it exceeds the 14,400pt limit."""
    path = base_path + ".pdf"
    H = arr.shape[0]
    page_dev_max = int(PDF_PAGE_MAX_CSS * scale)

    pages: List[bytes] = []
    y = 0
    while y < H:
        target = min(y + page_dev_max, H)
        if target < H:
            target = find_split_row(arr, target, search=int(200 * scale))
            if target <= y:
                target = min(y + page_dev_max, H)
        buf = io.BytesIO()
        Image.fromarray(arr[y:target], "RGB").save(buf, "PNG", optimize=False)
        pages.append(buf.getvalue())
        y = target

    # DPI = 96*scale makes each page css_px * 0.75 pt (image px / (96*scale) in
    # inches * 72 pt), i.e. "the page looks like the CSS layout at 1:1".
    dpi = 96 * scale
    layout = img2pdf.get_fixed_dpi_layout_fun((dpi, dpi))
    with open(path, "wb") as f:
        f.write(img2pdf.convert(pages, layout_fun=layout))
    return path


def save_outputs(arr: np.ndarray, out_dir: str, basename: str, scale: int,
                 fmt: str = "both") -> List[str]:
    """fmt: 'png' | 'pdf' | 'both'. Returns written file paths."""
    os.makedirs(out_dir, exist_ok=True)
    base_path = os.path.join(out_dir, basename)
    written: List[str] = []
    if fmt in ("png", "both"):
        written += save_png(arr, base_path)
    if fmt in ("pdf", "both"):
        written.append(save_pdf(arr, base_path, scale))
    return written
