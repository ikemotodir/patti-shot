"""Safety-mechanism verification for auto-update (検証指示書 section 4).

Induces each failure on purpose and checks the app survives it:
  A 通信不可      -> check fails silently, app continues (exit 0, no update)
  B DL失敗        -> Japanese error incl. manual-download hint; old exe intact
  C サイズ不一致  -> corrupt download rejected+removed; old exe intact
  D 置き換え失敗  -> updater bat restores the .bak; old exe intact; log shows it
  E ログ          -> update.log records every step (boss can copy-paste)

LOCALAPPDATA is redirected into the test dir so the real update.log stays
untouched.
"""
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(__file__)
SRC = os.path.abspath(os.path.join(HERE, "..", "src"))
TMP = os.path.join(os.environ["TEMP"], f"patti_shot_safety_{os.getpid()}")
PY = os.path.join(HERE, "..", ".venv", "Scripts", "python.exe")
LOG = os.path.join(TMP, "STUDIO PATTI", "PATTI SHOT", "update.log")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]


def run_app(env_extra):
    env = dict(os.environ)
    env["PATTI_SHOT_UPDATE_TEST"] = "1"
    env["PYTHONPATH"] = SRC
    env["LOCALAPPDATA"] = TMP          # redirect update.log
    env["PYTHONIOENCODING"] = "utf-8"  # child prints Japanese; match our decode
    env.update(env_extra)
    return subprocess.run([PY, "-m", "patti_shot"], env=env,
                          capture_output=True, text=True, timeout=180,
                          encoding="utf-8", errors="replace")


def read_log():
    try:
        return open(LOG, encoding="utf-8").read()
    except OSError:
        return ""


def main():
    shutil.rmtree(TMP, ignore_errors=True)
    os.makedirs(TMP, exist_ok=True)
    # leftover check must be a delta: %TEMP% is shared, an orphan from an older
    # run (or another app) would fail the test forever.
    pre_existing = set(f for f in os.listdir(os.environ["TEMP"])
                       if f.startswith("PATTI_SHOT_new_"))
    rundll = os.path.join(os.environ["SystemRoot"], "System32", "rundll32.exe")
    base = open(rundll, "rb").read()
    target = os.path.join(TMP, "PATTI_SHOT_target.exe")
    open(target, "wb").write(base + b"OLD")
    t0 = sha(target)
    results = {}

    # --- A: network unreachable -> silent normal continue ---
    r = run_app({"PATTI_SHOT_UPDATE_API": "http://127.0.0.1:9/nope",
                 "PATTI_SHOT_FAKE_EXE": target})
    results["A_net_down"] = (r.returncode == 0 and "no-update" in r.stdout
                             and "check: failed" in read_log())
    print(f"A 通信不可: exit={r.returncode} out={r.stdout.strip()!r} -> "
          f"{'PASS' if results['A_net_down'] else 'FAIL'}")

    # --- B: download fails (asset URL 404) -> JP message + old exe intact ---
    api = os.path.join(TMP, "b.json")
    json.dump({"tag_name": "v9.9.9", "assets": [{
        "name": "PATTI_SHOT.exe",
        "browser_download_url": "file:///" + TMP.replace("\\", "/") + "/missing.exe",
        "size": 123}]}, open(api, "w"))
    r = run_app({"PATTI_SHOT_UPDATE_API": "file:///" + api.replace("\\", "/"),
                 "PATTI_SHOT_FAKE_EXE": target})
    results["B_dl_fail"] = (r.returncode == 1 and "ダウンロードに失敗" in r.stdout
                            and "配布ページ" in r.stdout and sha(target) == t0)
    print(f"B DL失敗: exit={r.returncode} msg_ok={'ダウンロードに失敗' in r.stdout} "
          f"hint_ok={'配布ページ' in r.stdout} exe_intact={sha(target) == t0} -> "
          f"{'PASS' if results['B_dl_fail'] else 'FAIL'}")

    # --- C: size mismatch (corrupt download) -> rejected, removed, intact ---
    bad = os.path.join(TMP, "bad.exe")
    open(bad, "wb").write(b"corrupt")
    api2 = os.path.join(TMP, "c.json")
    json.dump({"tag_name": "v9.9.9", "assets": [{
        "name": "PATTI_SHOT.exe",
        "browser_download_url": "file:///" + bad.replace("\\", "/"),
        "size": 999_999_999}]}, open(api2, "w"))
    r = run_app({"PATTI_SHOT_UPDATE_API": "file:///" + api2.replace("\\", "/"),
                 "PATTI_SHOT_FAKE_EXE": target})
    leftovers = [f for f in os.listdir(os.environ["TEMP"])
                 if f.startswith("PATTI_SHOT_new_") and f not in pre_existing]
    results["C_size"] = (r.returncode == 1 and "サイズが一致しません" in r.stdout
                         and "配布ページ" in r.stdout and sha(target) == t0
                         and not leftovers)
    print(f"C サイズ不一致: exit={r.returncode} msg_ok={'サイズが一致しません' in r.stdout} "
          f"exe_intact={sha(target) == t0} temp_leftover={len(leftovers)} -> "
          f"{'PASS' if results['C_size'] else 'FAIL'}")

    # --- D: replace fails (new exe locked no-share) -> .bak restored ---
    new_exe = os.path.join(TMP, "new.exe")
    open(new_exe, "wb").write(base + b"NEW")
    GENERIC_READ = 0x80000000
    OPEN_EXISTING = 3
    stop = threading.Event()

    def hold():
        h = ctypes.windll.kernel32.CreateFileW(new_exe, GENERIC_READ, 0, None,
                                               OPEN_EXISTING, 0, None)
        stop.wait(120)  # keep locked through all (few) retries, then release
        ctypes.windll.kernel32.CloseHandle(h)

    th = threading.Thread(target=hold, daemon=True)
    th.start()
    time.sleep(0.3)
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC
    env["LOCALAPPDATA"] = TMP
    # small retry cap so the fail->restore path completes deterministically
    # (same code path as production's 120, just fewer iterations)
    code = ("import sys; sys.path.insert(0, r'%s'); from patti_shot import update; "
            "update.spawn_updater(r'%s', r'%s', max_retry=6); print('spawned')"
            % (SRC, target, new_exe))
    subprocess.run([PY, "-c", code], env=env, capture_output=True, text=True, timeout=60)
    print("D: updater spawned; waiting for replace-fail -> restore (~15s)...", flush=True)
    deadline = time.time() + 120
    restored = False
    while time.time() < deadline:
        log = read_log()
        if "restore ok" in log or "restore FAIL" in log:
            restored = "restore ok" in log
            break
        time.sleep(5)
    stop.set()
    bak_left = os.path.exists(target + ".bak")
    results["D_restore"] = (restored and sha(target) == t0 and not bak_left)
    print(f"D 置き換え失敗→復旧: restore_ok={restored} exe_intact={sha(target) == t0} "
          f"bak_cleaned={not bak_left} -> {'PASS' if results['D_restore'] else 'FAIL'}")

    # --- E: log completeness ---
    log = read_log()
    need = ["check:", "apply:", "[bat] updater start", "[bat] backup ok",
            "replace FAIL", "restore"]
    missing = [n for n in need if n not in log]
    results["E_log"] = not missing
    print(f"E ログ: missing={missing} path={LOG} -> {'PASS' if results['E_log'] else 'FAIL'}")

    ok = all(results.values())
    print("SAFETY VERIFICATION:", "PASS" if ok else f"FAIL {results}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
