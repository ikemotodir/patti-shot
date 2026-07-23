"""実機E2E (検証指示書 section 2-3): 本物の v4.0.1 exe から実際に v4.1.0 へ
自動更新が最後まで通ることを、Avastが許可している唯一のパス
(build\\dist\\PATTI_SHOT.exe) 上で検証する。

Avast はこの1ファイルだけを例外登録しているため、旧版をこのパスに置いて起動し、
自己置き換え→再起動までを実パスで走らせる。build\\dist の現行exeは退避して最後に
必ず戻す。
"""
import glob
import os
import shutil
import ssl
import subprocess
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from patti_shot import update, browser  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

EXE = os.path.join(ROOT, "build", "dist", "PATTI_SHOT.exe")   # Avast-permitted path
BACKUP = EXE + ".v41bak"
WORK = os.path.join(os.path.dirname(EXE), "e2e_work")
FROM_TAG, TO_TAG = "v4.0.1", "v4.1.0"
REL = "https://github.com/ikemotodir/patti-shot/releases/download/{}/PATTI_SHOT.exe"
COOKIE = {"name": "patti_e2e_login", "value": "kept-42", "domain": "example.com",
          "path": "/", "expires": 4102444800}


def dl(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "e2e"})
    with urllib.request.urlopen(req, timeout=180, context=update._ssl_context()) as r, \
            open(dest, "wb") as f:
        f.write(r.read())


def seed_cookie():
    with sync_playwright() as p:
        lr = browser.launch(p, browser.default_profile_dir(), headless=True,
                            viewport={"width": 800, "height": 600})
        lr.context.add_cookies([COOKIE])
        lr.context.close()


def cookie_alive():
    with sync_playwright() as p:
        lr = browser.launch(p, browser.default_profile_dir(), headless=True,
                            viewport={"width": 800, "height": 600})
        got = {c["name"]: c["value"] for c in lr.context.cookies("https://example.com/")}
        lr.context.close()
    return got.get(COOKIE["name"]) == COOKIE["value"]


def procs():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq PATTI_SHOT.exe", "/FO", "CSV"],
                         capture_output=True, text=True).stdout
    return [l for l in out.splitlines() if "PATTI_SHOT.exe" in l]


def main():
    os.makedirs(WORK, exist_ok=True)
    had_backup = os.path.exists(EXE)
    if had_backup:
        shutil.copy2(EXE, BACKUP)
    checks = {}
    try:
        print(f"[1] stage REAL {FROM_TAG} at the Avast-permitted path ...", flush=True)
        v41 = os.path.join(WORK, "v410.exe")
        if os.path.exists(BACKUP):
            shutil.copy2(BACKUP, v41)  # keep the real v4.1.0 for size compare
        dl(REL.format(FROM_TAG), EXE)
        old_size = os.path.getsize(EXE)
        to_size = os.path.getsize(v41) if os.path.exists(v41) else None
        print(f"    old(v4.0.1)={old_size}  target(v4.1.0)={to_size}", flush=True)

        print("[2] seed login cookie ...", flush=True)
        seed_cookie()

        # Relaunch proof from update.log: every exe logs an update-check line on
        # startup. The OLD (v4.0.1) exe logs "current=4.0.1"; only the relaunched
        # NEW exe logs "current=4.1.0". So a NEW "current=4.1.0" line appearing
        # after the old exe exits (and before we run our own [5]) proves the
        # updater auto-relaunched the new version. (v4.0.1's updater bat predates
        # the "relaunch issued" log line, so we cannot rely on that.)
        logp = update.log_path()
        n0 = len(open(logp, encoding="utf-8", errors="replace").read().splitlines()) \
            if os.path.exists(logp) else 0
        print("[3] launch OLD exe (real check -> download -> replace -> relaunch) ...", flush=True)
        env = dict(os.environ)
        env["PATTI_SHOT_UPDATE_TEST"] = "1"   # relaunched exe inherits this -> exits fast, no window
        r = subprocess.run([EXE], env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600)
        out = (r.stdout or "").strip()
        print("    old exe stdout:", out, flush=True)
        checks["#1-3 検知/DL/置換要求"] = f"found={TO_TAG}" in out and "applied=True" in out

        print("[4] wait for replace + auto-relaunch (new-version startup in update.log) ...", flush=True)
        relaunched, relaunch_check = False, ""
        for _ in range(150):
            time.sleep(2)
            tail = open(logp, encoding="utf-8", errors="replace").read().splitlines()[n0:]
            hits = [l for l in tail if "check: current=4.1.0" in l and "up to date" in l]
            if hits:
                relaunched, relaunch_check = True, hits[-1]
                break
        time.sleep(5)
        new_size = os.path.getsize(EXE)
        print(f"    exe {old_size} -> {new_size}  relaunch_check='{relaunch_check}'", flush=True)
        checks["#4 自動再起動"] = relaunched
        checks["#5/#10 新版起動・誤検知なし"] = "current=4.1.0" in relaunch_check and "up to date" in relaunch_check
        checks["#3 置き換え(サイズがv4.1.0)"] = (to_size is not None and new_size == to_size)

        print("[5] capture with the UPDATED exe (#7) ...", flush=True)
        shots = os.path.join(WORK, "shots")
        shutil.rmtree(shots, ignore_errors=True)
        env2 = dict(os.environ)
        env2["PATTI_SHOT_SELFTEST"] = "https://example.com/"
        env2["PATTI_SHOT_OUT_DIR"] = shots
        env2["PATTI_SHOT_NO_OPEN"] = "1"
        r2 = subprocess.run([EXE], env=env2, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=300)
        pngs = glob.glob(os.path.join(shots, "*.png"))
        pdfs = glob.glob(os.path.join(shots, "*.pdf"))
        checks["#7 更新後の撮影"] = '"ok": true' in (r2.stdout or "") and len(pngs) == 1 and len(pdfs) == 1
        print(f"    selftest ok={'\"ok\": true' in (r2.stdout or '')} png={len(pngs)} pdf={len(pdfs)}", flush=True)

        print("[6] leftovers / processes / cookie ...", flush=True)
        tmp = os.environ["TEMP"]
        lo = (glob.glob(os.path.join(tmp, "PATTI_SHOT_new_*.exe"))
              + glob.glob(os.path.join(tmp, "patti_shot_update_*.bat"))
              + glob.glob(EXE + ".bak"))
        checks["#8 後始末(一時ファイルなし)"] = not lo
        checks["#9 プロセス残なし"] = len(procs()) == 0
        checks["#6 ログイン(Cookie)維持"] = cookie_alive()
        print(f"    leftovers={len(lo)} procs={len(procs())} cookie={checks['#6 ログイン(Cookie)維持']}", flush=True)
    finally:
        if had_backup and os.path.exists(BACKUP):
            try:
                shutil.copy2(BACKUP, EXE)
                os.remove(BACKUP)
            except Exception as e:
                print("  [restore build/dist WARN]", e, flush=True)

    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}", flush=True)
    ok = checks and all(checks.values())
    print("LIVE E2E:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
