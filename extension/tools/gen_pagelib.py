"""Regenerate extension/pagelib.js from the verified engine (src/patti_shot/jslib.py).

The extension must run the exact page-side logic that the 15-page harness
verifies, so it is generated rather than hand-copied.

    python extension/tools/gen_pagelib.py
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))

from patti_shot.jslib import BROWSER_JS  # noqa: E402

HEADER = """// PATTI SHOT - page-side capture logic (STEP1 preprocessing / STEP2 real content
// height measurement / fixed-element neutralisation / restore).
//
// GENERATED from src/patti_shot/jslib.py so the extension runs the exact engine
// that the 15-page verification harness passes. Do not hand-edit: change
// jslib.py and regenerate with extension/tools/gen_pagelib.py.
"""

out = os.path.join(ROOT, "extension", "pagelib.js")
with io.open(out, "w", encoding="utf-8", newline="\n") as f:
    f.write(HEADER + BROWSER_JS)
print(f"wrote {out} ({len(BROWSER_JS)} chars of engine JS)")
