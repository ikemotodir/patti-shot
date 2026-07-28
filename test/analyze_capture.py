"""Read a saved PATTI SHOT capture back and find repeated / missing rows.

The boss keeps seeing the same row numbers twice. Height and blank checks pass
on a broken image, so this works on the picture itself: it hashes narrow
horizontal strips and reports any strip that appears more than once far away
from itself, which is exactly what a mis-stitched capture looks like.

Usage:  analyze_capture.py <file.pdf|file.png> [--strip 12] [--out DIR]
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


def load(path):
    """Return the whole capture as one uint8 array (H, W, 3)."""
    if path.lower().endswith(".pdf"):
        # Render each PAGE in page order. Pulling embedded images by xref is
        # not safe here: the resource list order is not the page order, and a
        # scrambled stack would invent duplicates that are not in the file.
        import fitz
        doc = fitz.open(path)
        parts = []
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), colorspace=fitz.csRGB)
            arr = np.frombuffer(pix.samples, dtype=np.uint8)
            parts.append(arr.reshape(pix.height, pix.width, 3).copy())
        doc.close()
        w = min(p.shape[1] for p in parts)
        return np.vstack([p[:, :w] for p in parts])
    return np.array(Image.open(path).convert("RGB"))


def strip_hashes(img, strip):
    """hash of every `strip`-tall block, plus whether it is near-uniform"""
    h = (img.shape[0] // strip) * strip
    blocks = img[:h].reshape(-1, strip, img.shape[1], 3)
    keys, flat = [], []
    for i in range(blocks.shape[0]):
        b = blocks[i]
        keys.append(hash(b.tobytes()))
        flat.append(b.std() < 6)
    return keys, np.array(flat)


def main():
    path = sys.argv[1]
    strip = 12
    outdir = None
    for i, a in enumerate(sys.argv):
        if a == "--strip":
            strip = int(sys.argv[i + 1])
        if a == "--out":
            outdir = sys.argv[i + 1]

    img = load(path)
    H, W = img.shape[0], img.shape[1]
    print(f"画像 {W}x{H}", flush=True)

    keys, uniform = strip_hashes(img, strip)
    n = len(keys)
    pos = {}
    dups = []
    for i, k in enumerate(keys):
        if uniform[i]:
            continue
        if k in pos:
            dups.append((pos[k], i))
        pos.setdefault(k, i)

    print(f"帯 {n}本（{strip}px毎） / 同一帯の再出現 {len(dups)}件", flush=True)

    # group consecutive duplicate pairs with the same offset into runs
    runs = []
    for first, second in dups:
        off = second - first
        if runs and runs[-1][2] == off and second == runs[-1][1] + 1:
            runs[-1][1] = second
            runs[-1][3] += 1
        else:
            runs.append([second, second, off, 1])
    runs = [r for r in runs if r[3] * strip >= 40]     # ignore tiny coincidences
    runs.sort(key=lambda r: -r[3])
    print(f"まとまった重複ブロック {len(runs)}件（40px以上）", flush=True)
    total = 0
    for s, e, off, cnt in runs[:40]:
        y0, y1 = s * strip, (e + 1) * strip
        src = (s - off) * strip
        total += cnt * strip
        print(f"   y={y0}..{y1} ({cnt * strip}px) は y={src} の再出現（{off * strip}px下）",
              flush=True)
    print(f"重複総量 約{total}px（画像の{total / H * 100:.1f}%）", flush=True)

    if outdir and runs:
        os.makedirs(outdir, exist_ok=True)
        for i, (s, e, off, cnt) in enumerate(runs[:6]):
            y0 = max(0, (s - off) * strip - 40)
            a = img[y0:y0 + min(900, (cnt * strip) + 120)]
            b = img[max(0, s * strip - 40):max(0, s * strip - 40) + a.shape[0]]
            pair = np.hstack([a, np.full((a.shape[0], 24, 3), 255, np.uint8),
                              b[:a.shape[0]]])
            Image.fromarray(pair).save(os.path.join(outdir, f"dup{i + 1}.png"))
        print(f"比較画像を {outdir} に保存", flush=True)


if __name__ == "__main__":
    main()
