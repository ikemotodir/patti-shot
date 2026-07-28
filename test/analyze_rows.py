"""Row-level check of a saved capture: is any table row present twice, or missing?

Strip hashing only finds repeats whose distance happens to be a multiple of the
strip height, which is how a first look at the boss's file reported "everything
is 1092px apart" - that was the method, not the file. This anchors on the table's
own horizontal rules instead, so a row is compared as a row no matter where it
sits.

Usage:  analyze_rows.py <file.pdf|file.png> [--out DIR]
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


def load(path):
    """The capture at its original resolution, pages in page order."""
    if path.lower().endswith(".pdf"):
        import fitz
        doc = fitz.open(path)
        parts = []
        for page in doc:
            drawn = page.get_image_info(xrefs=True)
            drawn = [d for d in drawn if d.get("xref")]
            drawn.sort(key=lambda d: d["bbox"][1])
            for d in drawn:
                pix = fitz.Pixmap(doc, d["xref"])
                if pix.n > 3:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                arr = np.frombuffer(pix.samples, dtype=np.uint8)
                parts.append(arr.reshape(pix.height, pix.width, pix.n)[:, :, :3].copy())
        doc.close()
        if not parts:
            raise SystemExit("PDFから画像を取り出せませんでした")
        w = min(p.shape[1] for p in parts)
        return np.vstack([p[:, :w] for p in parts])
    return np.array(Image.open(path).convert("RGB"))


def find_rules(grey, x0, x1):
    """y positions of horizontal rules (table row separators)"""
    band = grey[:, x0:x1]
    dark = (band < 210).mean(axis=1)
    return np.where(dark > 0.9)[0]


def main():
    path = sys.argv[1]
    outdir = None
    for i, a in enumerate(sys.argv):
        if a == "--out":
            outdir = sys.argv[i + 1]

    img = load(path)
    H, W = img.shape[0], img.shape[1]
    grey = (img[:, :, 0] * 0.299 + img[:, :, 1] * 0.587 + img[:, :, 2] * 0.114)
    print(f"画像 {W}x{H}", flush=True)

    # the table occupies the middle; use the widest run of horizontal rules
    x0, x1 = int(W * 0.20), int(W * 0.80)
    rules = find_rules(grey, x0, x1)
    if len(rules) < 20:
        x0, x1 = int(W * 0.10), int(W * 0.90)
        rules = find_rules(grey, x0, x1)
    # collapse adjacent rule pixels into single lines
    lines = []
    for y in rules:
        if not lines or y - lines[-1] > 3:
            lines.append(int(y))
        else:
            lines[-1] = int(y)
    print(f"横罫線 {len(lines)}本 検出", flush=True)

    rows = []
    for a, b in zip(lines, lines[1:]):
        h = b - a
        if h < 20 or h > 600:
            continue
        rows.append((a, b))
    print(f"表の行 {len(rows)}行", flush=True)

    # fingerprint each row on its content, scale-normalised so rows of
    # different heights are still comparable
    seen = {}
    dups = []
    for a, b in rows:
        block = img[a + 2:b - 2, x0:x1]
        if block.size == 0:
            continue
        small = np.array(Image.fromarray(block).resize((96, 24), Image.BILINEAR))
        g = (small[:, :, 0] * 0.299 + small[:, :, 1] * 0.587 + small[:, :, 2] * 0.114)
        if g.std() < 8:
            continue
        key = (np.round(g / 16).astype(np.uint8)).tobytes()
        if key in seen:
            dups.append((seen[key], (a, b)))
        else:
            seen[key] = (a, b)

    print(f"内容が同一の行ペア: {len(dups)}件", flush=True)
    for (pa, pb), (qa, qb) in dups[:25]:
        print(f"   y={pa}..{pb} と y={qa}..{qb}（{qa - pa}px 離れ）", flush=True)

    if outdir and dups:
        os.makedirs(outdir, exist_ok=True)
        for i, ((pa, pb), (qa, qb)) in enumerate(dups[:8]):
            h = max(pb - pa, qb - qa)
            a = img[pa:pa + h]
            b = img[qa:qa + h]
            n = min(a.shape[0], b.shape[0])
            pair = np.vstack([a[:n], np.full((10, W, 3), 255, np.uint8), b[:n]])
            Image.fromarray(pair).save(os.path.join(outdir, f"row{i + 1}.png"))
        print(f"比較画像を {outdir} に保存", flush=True)


if __name__ == "__main__":
    main()
