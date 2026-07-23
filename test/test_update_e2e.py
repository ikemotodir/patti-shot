"""Condition 9 end-to-end: a real old exe updates itself from the real GitHub
release and relaunches.

Builds a v3.9.9 exe (temporarily patching __version__, then restoring), runs it
with PATTI_SHOT_UPDATE_TEST: it must find v4.0.0 on GitHub, download the real
asset, hand off to the updater batch, get replaced, and the relaunched (new)
exe writes a marker proving it runs the new version. Zero human interaction.
"""
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
INIT = os.path.join(ROOT, "src", "patti_shot", "__init__.py")
TMP = os.path.join(os.environ["TEMP"], f"patti_shot_e2e_{os.getpid()}")


def set_version(v: str) -> None:
    src = open(INIT, encoding="utf-8").read()
    src = re.sub(r'__version__ = "[^"]+"', f'__version__ = "{v}"', src)
    open(INIT, "w", encoding="utf-8").write(src)


def main():
    os.makedirs(TMP, exist_ok=True)
    orig = open(INIT, encoding="utf-8").read()
    m = re.search(r'__version__ = "([^"]+)"', orig)
    real_ver = m.group(1)
    old_exe = os.path.join(TMP, "PATTI_SHOT.exe")
    try:
        print(f"building fake old exe (3.9.9), real version={real_ver} ...", flush=True)
        set_version("3.9.9")
        r = subprocess.run(
            [PY, "-m", "PyInstaller", "--noconfirm", "--onefile", "--name", "PATTI_SHOT_OLD",
             "--paths", os.path.join(ROOT, "src"), "--collect-all", "playwright",
             "--hidden-import", "patti_shot",
             "--distpath", os.path.join(TMP, "dist"),
             "--workpath", os.path.join(TMP, "work"),
             "--specpath", TMP,
             os.path.join(ROOT, "build", "entry.py")],
            capture_output=True, text=True, timeout=600)
        assert r.returncode == 0, "old build failed: " + r.stderr[-800:]
    finally:
        open(INIT, "w", encoding="utf-8").write(orig)  # always restore version

    shutil.copy2(os.path.join(TMP, "dist", "PATTI_SHOT_OLD.exe"), old_exe)
    size_before = os.path.getsize(old_exe)

    marker = os.path.join(TMP, "marker.txt")
    env = dict(os.environ)
    env["PATTI_SHOT_UPDATE_TEST"] = "1"
    env["PATTI_SHOT_UPDATE_MARKER"] = marker

    print("running old exe (checks real GitHub, downloads ~91MB) ...", flush=True)
    r = subprocess.run([old_exe], env=env, capture_output=True, text=True, timeout=600)
    print("old exe stdout:", r.stdout.strip(), flush=True)
    assert "found=v" in r.stdout and "applied=True" in r.stdout, "update not applied"

    # wait for the updater batch: replace + relaunch (relaunched exe appends to
    # the marker; give the 91MB copy + AV scan + relaunch up to 5 minutes)
    print("waiting for replacement + relaunch ...", flush=True)
    deadline = time.time() + 300
    lines = []
    while time.time() < deadline:
        time.sleep(3)
        if os.path.exists(marker):
            lines = [l.strip() for l in open(marker, encoding="utf-8") if l.strip()]
            if any("no-update" in l for l in lines):
                break
    size_after = os.path.getsize(old_exe)
    print("marker lines:", lines, flush=True)
    print(f"exe size: {size_before} -> {size_after}", flush=True)

    ok = (any(f"current={real_ver} no-update" in l for l in lines)
          and size_after != size_before)
    print("UPDATE E2E:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
