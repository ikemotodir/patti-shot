"""Verify the auto-update mechanism (spec section 5 / condition 9) locally.

Uses a fake latest-release JSON + fake exe served via file:// URLs:
check -> download -> updater batch replaces the (locked-then-released) target
-> temp file cleaned up. The relaunch step is verified in the real E2E test
against the actual GitHub release (test_update_e2e in REPORT).

The fake exes are rundll32.exe copies with overlay bytes (distinct content,
still silently executable, no window) so an accidental start is harmless.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(__file__)
SRC = os.path.join(HERE, "..", "src")
TMP = os.path.join(os.environ["TEMP"], f"patti_shot_update_test_{os.getpid()}")
PY = os.path.join(HERE, "..", ".venv", "Scripts", "python.exe")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]


def main():
    shutil.rmtree(TMP, ignore_errors=True)
    os.makedirs(TMP, exist_ok=True)
    rundll = os.path.join(os.environ["SystemRoot"], "System32", "rundll32.exe")
    base = open(rundll, "rb").read()
    old_exe = os.path.join(TMP, "PATTI_SHOT_target.exe")
    new_exe = os.path.join(TMP, "new_asset.exe")
    open(old_exe, "wb").write(base + b"OLD-VERSION-MARKER")
    open(new_exe, "wb").write(base + b"NEW-VERSION-MARKER-9.9.9")

    api = os.path.join(TMP, "latest.json")
    json.dump({
        "tag_name": "v9.9.9",
        "assets": [{"name": "PATTI_SHOT.exe",
                    "browser_download_url": "file:///" + new_exe.replace("\\", "/"),
                    "size": os.path.getsize(new_exe)}],
    }, open(api, "w"))

    env = dict(os.environ)
    env["PATTI_SHOT_UPDATE_TEST"] = "1"
    env["PATTI_SHOT_UPDATE_API"] = "file:///" + api.replace("\\", "/")
    env["PATTI_SHOT_FAKE_EXE"] = old_exe
    env["PYTHONPATH"] = os.path.abspath(SRC)

    # hold an exclusive (no-share) handle on the target for ~6s, simulating the
    # still-running exe: the updater batch must wait and retry, not give up.
    import ctypes
    import threading
    GENERIC_READ = 0x80000000
    OPEN_EXISTING = 3

    def hold_lock():
        h = ctypes.windll.kernel32.CreateFileW(old_exe, GENERIC_READ, 0, None,
                                               OPEN_EXISTING, 0, None)
        time.sleep(6)
        ctypes.windll.kernel32.CloseHandle(h)

    before = sha(old_exe)
    locker = threading.Thread(target=hold_lock, daemon=True)
    locker.start()
    time.sleep(0.2)

    r = subprocess.run([PY, "-m", "patti_shot"], env=env,
                       capture_output=True, text=True, timeout=120)
    print("stdout:", r.stdout.strip())
    ok_run = r.returncode == 0 and "found=v9.9.9 applied=True" in r.stdout

    # updater batch waits ~1s ticks; give it time to replace the target.
    # While our simulated lock is held, reads fail too -- treat as "not yet".
    replaced = False
    for _ in range(30):
        time.sleep(1)
        try:
            if sha(old_exe) == sha(new_exe):
                replaced = True
                break
        except PermissionError:
            continue
    after = sha(old_exe)
    print(f"target hash: {before} -> {after} (new_asset={sha(new_exe)}) replaced={replaced}")

    # temp download should be cleaned up by the batch
    time.sleep(3)
    leftovers = [f for f in os.listdir(os.environ["TEMP"])
                 if f.startswith("PATTI_SHOT_new_")]
    print(f"leftover temp downloads: {len(leftovers)}")

    ok = ok_run and replaced and len(leftovers) == 0
    print("UPDATE MECHANISM:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
