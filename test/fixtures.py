"""Deterministic local HTML fixtures for the verification harness.

Each fixture is self-contained (inline CSS/JS, no network) and exercises one of
the structural categories from spec section 6. Generated into test/fixtures/
and served via file:// so the harness is fully reproducible.
"""
from __future__ import annotations

import base64
import os

FIX_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _svg_img(i: int, w: int = 760, h: int = 340) -> str:
    """A base64 data-URI SVG with a diagonal gradient (varied pixels) + label."""
    a = (i * 47) % 360
    b = (i * 47 + 140) % 360
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}'>"
           f"<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
           f"<stop offset='0' stop-color='hsl({a},70%,55%)'/>"
           f"<stop offset='1' stop-color='hsl({b},70%,35%)'/></linearGradient></defs>"
           f"<rect width='100%' height='100%' fill='url(#g)'/>"
           f"<text x='30' y='{h//2}' font-size='44' fill='#fff' "
           f"font-family='sans-serif'>image {i}</text></svg>")
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()

_HEAD = """<!doctype html><html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{css}</style></head><body>"""


def _para(i: int) -> str:
    return (f"<p>Section {i}: The quick brown fox jumps over the lazy dog. "
            f"Keyword-{i}-alpha bravo charlie delta echo foxtrot golf hotel india "
            f"juliet kilo lima mike november-{i} oscar papa quebec romeo sierra.</p>")


def _jpara(i: int) -> str:
    return (f"<p>第{i}節：吾輩は猫である。名前はまだ無い。どこで生れたか"
            f"見当がつかぬ。キーワード{i}番。日本語のフォントで表示される段落"
            f"であり、縦に長い文章を測定するための実データとして用いる。</p>")


def short() -> str:
    css = "body{font:16px/1.6 sans-serif;margin:40px;max-width:760px}"
    body = "<h1>Short page</h1>" + _para(1) + _para(2)
    return _HEAD.format(lang="en", title="short", css=css) + body + "</body></html>"


def long_page() -> str:
    css = "body{font:16px/1.6 sans-serif;margin:0 40px}h1{color:#0a5}"
    body = "<h1>Very long page (>20000px)</h1>" + "".join(_para(i) for i in range(1, 340))
    return _HEAD.format(lang="en", title="long", css=css) + body + "</body></html>"


def lazy() -> str:
    # 30 real lazy-loaded images (varied gradients) each with a text caption.
    css = """body{font:16px/1.6 sans-serif;margin:0 30px}
    .item{margin:18px 0}.item img{display:block;width:760px;max-width:100%;height:auto}
    .cap{padding:8px 0;color:#333}"""
    items = "".join(
        f'<div class="item"><img loading="lazy" src="{_svg_img(i)}" alt="image {i}">'
        f'<div class="cap">Caption {i}: keyword-lazy-{i} bravo charlie delta echo</div></div>'
        for i in range(1, 31))
    return _HEAD.format(lang="en", title="lazy", css=css) + "<h1>Lazy images page</h1>" + items + "</body></html>"


def fixed_header() -> str:
    css = """body{font:16px/1.6 sans-serif;margin:0;padding-top:60px}
    header{position:fixed;top:0;left:0;right:0;height:56px;background:#c0287a;color:#fff;
    display:flex;align-items:center;padding:0 20px;z-index:10}
    .sticky{position:sticky;top:56px;background:#ffd;padding:8px 20px;border-bottom:1px solid #ccc}
    .cookie{position:fixed;bottom:0;left:0;right:0;background:#222;color:#fff;padding:12px 20px}
    .content{padding:0 20px}"""
    body = ('<header>PATTI SHOT — fixed header keyword-header</header>'
            '<div class="sticky">Sticky sub-banner keyword-sticky</div>'
            '<div class="content"><h1>Fixed header page</h1>'
            + "".join(_para(i) for i in range(1, 60))
            + '</div><div class="cookie">Cookie banner keyword-cookie</div>')
    return _HEAD.format(lang="en", title="fixedheader", css=css) + body + "</body></html>"


def inner_scroll() -> str:
    css = """body{font:16px/1.6 sans-serif;margin:0}
    .wrap{display:flex;flex-direction:column;height:100vh}
    .top{background:#eef;padding:16px 20px}
    .scroller{flex:1;overflow-y:auto;padding:0 20px;border-top:2px solid #99f}"""
    inner = "".join(_para(i) for i in range(1, 120))
    body = ('<div class="wrap"><div class="top"><h1>Inner scroll container keyword-top</h1></div>'
            f'<div class="scroller" id="sc">{inner}</div></div>')
    return _HEAD.format(lang="en", title="innerscroll", css=css) + body + "</body></html>"


def infinite() -> str:
    css = """body{font:16px/1.6 sans-serif;margin:0 40px}.item{padding:6px 0;border-bottom:1px solid #eee}"""
    js = """<script>
    let n=0; const cap=600;
    function add(k){for(let i=0;i<k&&n<cap;i++){n++;const d=document.createElement('div');
      d.className='item'; d.textContent='Row '+n+' keyword-row-'+n+' lorem ipsum dolor sit amet';
      document.body.appendChild(d);}}
    add(30);
    window.addEventListener('scroll',()=>{ if(window.scrollY+window.innerHeight > document.body.scrollHeight-800) add(30); });
    </script>"""
    body = "<h1>Infinite scroll (cutoff test) keyword-inf</h1>" + js
    return _HEAD.format(lang="en", title="infinite", css=css) + body + "</body></html>"


def wide() -> str:
    cols = 24
    css = """body{font:15px/1.5 sans-serif;margin:0}
    table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:6px 14px;white-space:nowrap}
    th{background:#c0287a;color:#fff}"""
    header = "<tr>" + "".join(f"<th>Col-{c} keyword-col-{c}</th>" for c in range(cols)) + "</tr>"
    rows = "".join("<tr>" + "".join(f"<td>r{r}c{c} value-{r}-{c}</td>" for c in range(cols)) + "</tr>"
                   for r in range(1, 40))
    body = f"<h1>Wide table (horizontal scroll)</h1><table>{header}{rows}</table>"
    return _HEAD.format(lang="en", title="wide", css=css) + body + "</body></html>"


def japanese() -> str:
    css = "body{font:17px/1.9 'Yu Gothic','Meiryo',sans-serif;margin:0 48px}h1{color:#b03}"
    body = "<h1>日本語フォント中心のページ</h1>" + "".join(_jpara(i) for i in range(1, 120))
    return _HEAD.format(lang="ja", title="japanese", css=css) + body + "</body></html>"


def tables() -> str:
    css = """body{font:15px/1.5 sans-serif;margin:0 30px}
    table{border-collapse:collapse;margin:18px 0;width:100%}td,th{border:1px solid #bbb;padding:6px 10px}
    th{background:#eee}"""
    def tbl(t):
        head = "<tr>" + "".join(f"<th>H{c} key-{t}-{c}</th>" for c in range(6)) + "</tr>"
        rows = "".join("<tr>" + "".join(f"<td>t{t}r{r}c{c}</td>" for c in range(6)) + "</tr>"
                       for r in range(12))
        return f"<h2>Table {t}</h2><table>{head}{rows}</table>"
    body = "<h1>Many tables page</h1>" + "".join(tbl(t) for t in range(1, 12))
    return _HEAD.format(lang="en", title="tables", css=css) + body + "</body></html>"


def iframe() -> str:
    inner = ("<style>body{font:16px/1.6 sans-serif;margin:20px;background:#f6f6ff}</style>"
             "<h2>Iframe content keyword-iframe</h2>"
             + "".join(f"<p>Inner paragraph {i} keyword-inner-{i}.</p>" for i in range(1, 25)))
    inner_attr = inner.replace('"', "&quot;")
    css = "body{font:16px/1.6 sans-serif;margin:0 40px}iframe{width:100%;height:1400px;border:2px solid #c0287a}"
    body = ("<h1>Page with iframe keyword-host</h1>"
            + "".join(_para(i) for i in range(1, 10))
            + f'<iframe srcdoc="{inner_attr}"></iframe>'
            + "".join(_para(i) for i in range(10, 20)))
    return _HEAD.format(lang="en", title="iframe", css=css) + body + "</body></html>"


def dark() -> str:
    # A normal dark-theme page: dark background with light text throughout.
    # Purpose (cat 12): confirm blank detection does NOT misfire on dark themes.
    css = """body{font:16px/1.7 sans-serif;margin:0;background:#0e0e12;color:#e8e8ef}
    header{background:#171722;padding:20px 40px}h1{color:#8ab4ff;margin:0}
    .content{padding:0 40px}a{color:#8ab4ff}"""
    body = ('<header><h1>Dark theme page keyword-dark</h1></header><div class="content">'
            + "".join(_para(i) for i in range(1, 90)) + '</div>')
    return _HEAD.format(lang="en", title="dark", css=css) + body + "</body></html>"


FIXTURES = {
    "short": short, "long": long_page, "lazy": lazy, "fixedheader": fixed_header,
    "innerscroll": inner_scroll, "infinite": infinite, "wide": wide,
    "japanese": japanese, "tables": tables, "iframe": iframe, "dark": dark,
}


def build_fixtures() -> dict:
    """Write all fixtures and return {name: file_url}."""
    os.makedirs(FIX_DIR, exist_ok=True)
    out = {}
    for name, fn in FIXTURES.items():
        path = os.path.join(FIX_DIR, f"{name}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(fn())
        out[name] = "file:///" + path.replace("\\", "/")
    return out


if __name__ == "__main__":
    for n, u in build_fixtures().items():
        print(f"{n}: {u}")
