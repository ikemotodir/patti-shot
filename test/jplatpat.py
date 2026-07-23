"""J-PlatPat trademark-search automation for the harness (spec section 6, #1).

navigate(page) drives the trademark simple-search (t0100) to a results page and
returns (reached: bool, info: str). If results can't be reached the harness
records the page as 未検証 -- never a fake PASS.
"""
from __future__ import annotations

SEARCH_URL = "https://www.j-platpat.inpit.go.jp/t0100"
TERM = "ソニー"  # a common registered mark -> many hits -> a long results page


def _click_search(page) -> bool:
    # The 検索 button is a Material button; try several strategies.
    for loc in (
        page.get_by_role("button", name="検索", exact=True),
        page.locator("button:has-text('検索')"),
        page.locator("button", has_text="検索"),
    ):
        try:
            if loc.count() > 0:
                loc.first.click(timeout=8000)
                return True
        except Exception:
            continue
    # last resort: any element whose exact trimmed text is 検索
    try:
        page.evaluate("""() => {
          const els = Array.from(document.querySelectorAll('button,a,span,div'));
          const t = els.find(e => (e.textContent||'').trim() === '検索' && e.offsetParent);
          if (t) t.click();
        }""")
        return True
    except Exception:
        return False


def _results_reached(page) -> bool:
    try:
        txt = page.evaluate("() => document.body ? document.body.innerText : ''")
    except Exception:
        txt = ""
    return ("検索結果一覧" in txt) or ("ヒット件数" in txt) or ("該当する結果" not in txt and "件" in txt and "検索結果" in txt)


def navigate(page) -> tuple[bool, str]:
    try:
        page.goto(SEARCH_URL, wait_until="networkidle", timeout=60000)
    except Exception as e:
        return False, f"goto失敗: {type(e).__name__}"
    page.wait_for_timeout(1500)

    ta = page.locator("#t01_srchCondtn_mk_txtKeywd0")
    try:
        ta.wait_for(state="visible", timeout=15000)
        ta.click()
        ta.fill(TERM)
    except Exception as e:
        return False, f"検索欄入力失敗: {type(e).__name__}"

    if not _click_search(page):
        return False, "検索ボタンが見つからない"

    # wait for results to render
    try:
        page.wait_for_load_state("networkidle", timeout=60000)
    except Exception:
        pass
    for _ in range(20):
        page.wait_for_timeout(1000)
        if _results_reached(page):
            hit = ""
            try:
                hit = page.evaluate(
                    "() => { const m=(document.body.innerText.match(/ヒット件数[^0-9]*([0-9,]+)/)||[])[1]; return m||''; }")
            except Exception:
                pass
            return True, f"検索語='{TERM}' 結果到達 url={page.url} ヒット={hit or '?'}"
    # dump a hint of what's on screen for the report
    snippet = ""
    try:
        snippet = page.evaluate("() => (document.body.innerText||'').replace(/\\s+/g,' ').slice(0,160)")
    except Exception:
        pass
    return False, f"結果ページ未到達 url={page.url} 画面='{snippet}'"
