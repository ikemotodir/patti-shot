"""Find rows that appear twice in a saved capture, at any distance.

Phase-independent on purpose: an earlier strip-hash version could only see
repeats whose distance was a multiple of the strip height, which made it report
"everything is 1092px apart" and miss the rest. This signs every single row, so
a repeat is found wherever it is.

Always run this on the PDF (or an un-downscaled PNG): a PNG that was shrunk to
fit one file resamples the pixels, and two identical regions at different
offsets no longer come out byte-identical - the check would pass on a broken
file.

Usage:  check_dupes.py <file.pdf|file.png>
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PIL import Image

from analyze_rows import load

Image.MAX_IMAGE_PIXELS = None


def find_repeats(img, min_rows=24, min_gap=200):
    H, W = img.shape[0], img.shape[1]
    x0, x1 = int(W * 0.28), int(W * 0.78)
    band = img[:, x0:x1:4].astype(np.float32)
    grey = band[:, :, 0] * 0.299 + band[:, :, 1] * 0.587 + band[:, :, 2] * 0.114
    sig = np.round(grey / 10).astype(np.int16)
    var = sig.std(axis=1)

    first, hits = {}, []
    for y in range(H):
        if var[y] < 1.2:
            continue
        k = hash(sig[y].tobytes())
        if k in first:
            if y - first[k] >= min_gap:
                hits.append((first[k], y))
        else:
            first[k] = y

    runs = []
    for a, b in hits:
        off = b - a
        if runs and runs[-1][2] == off and b <= runs[-1][1] + 3:
            runs[-1][1] = b
        else:
            runs.append([b, b, off])
    runs = [r for r in runs if r[1] - r[0] + 1 >= min_rows]
    runs.sort(key=lambda r: -(r[1] - r[0]))
    return runs


def main():
    path = sys.argv[1]
    img = load(path)
    print(f"{os.path.basename(path)}  {img.shape[1]}x{img.shape[0]}", flush=True)
    runs = find_repeats(img)
    total = sum(r[1] - r[0] + 1 for r in runs)
    print(f"二度出ている行のかたまり: {len(runs)}件 / 合計 {total}px", flush=True)
    for s, e, off in runs[:20]:
        print(f"   y={s}..{e} ({e - s + 1}px) は y={s - off} の再出現（{off}px 離れ）",
              flush=True)
    print("RESULT:", "CLEAN" if not runs else "DUPLICATED")
    sys.exit(0 if not runs else 1)


if __name__ == "__main__":
    main()
