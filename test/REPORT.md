# PATTI SHOT v4.0 自動検証レポート

- 生成: 2026-07-22 18:30:57
- OS: Windows-11-10.0.26200-SP0 / ブラウザ: chrome 150.0.0.0
- ウィンドウ(viewport): 1280x900
- Python: 3.14.6 / Playwright: 1.61

**合計 15件 : PASS 15 / FAIL 0 / ERROR・未検証 0**

| # | ページ | カテゴリ | 倍率 | 判定 | blank | height | duplicate | missing | ui_leak | resolution | cleanup | errors | truth |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | jplatpat | 1 商標検索結果(必須) | 2x | **PASS** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 2 | wiki_long | 2 縦20000px+ | 2x | **PASS** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 3 | wiki_images | 3/10 画像・表が多い | 2x | **PASS** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 4 | pythonorg | 実在サイト(一般) | 2x | **PASS** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 5 | long | 2 縦20000px+(fixture) | 2x | **PASS** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 6 | lazy | 3 遅延読込画像 | 2x | **PASS** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 7 | fixedheader | 4 固定ヘッダー+追従 | 2x | **PASS** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 8 | innerscroll | 5 内側スクロール | 2x | **PASS** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 9 | infinite | 6 無限スクロール(打切) | 2x | **PASS** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 10 | short | 7 短い1画面 | 2x | **PASS** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 11 | wide | 8 横スクロール | 2x | **PASS** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 12 | japanese | 9 日本語フォント | 3x | **PASS** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 13 | tables | 10 テーブル多数 | 2x | **PASS** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 14 | iframe | 11 iframe | 2x | **PASS** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 15 | dark | 12 ダークテーマ | 2x | **PASS** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

## 1. jplatpat — PASS
- カテゴリ: 1 商標検索結果(必須) / 種別: nav / 倍率: 2x
- 遷移: 検索語='ソニー' 結果到達 url=https://www.j-platpat.inpit.go.jp/t0100 ヒット=45
- 画像: 2560x16300px / 実測content=8154 scrollH=8154 capture=8154 / channel=
- 分割: split=True bands=10 attempts=1 trimmed=8px elapsed=8.3s
  - ✅ **blank**: runs=[](n=0)
  - ✅ **height**: img/2=8150 vs content=8154 tol=±245
  - ✅ **duplicate**: dup_run=12css px
  - ✅ **missing**: present=12 missing=0 of 12 欠落=[]
  - ✅ **ui_leak**: pink_px=0
  - ✅ **resolution**: img_w=2560 exp=2560(=1280x2)
  - ✅ **cleanup**: before=f7:s0:tag0:m0 after=f7:s0:tag0:m0
  - ✅ **errors**: our_errors=[] / page_noise=0件
  - ✅ **truth**: onscreen一致 worst=0.00 [(2853, 0.0), (4892, 0.0), (6930, 0.0)]

## 2. wiki_long — PASS
- カテゴリ: 2 縦20000px+ / 種別: live / 倍率: 2x
- 画像: 2560x63692px / 実測content=31850 scrollH=31850 capture=31850 / channel=
- 分割: split=True bands=36 attempts=1 trimmed=8px elapsed=14.2s
  - ✅ **blank**: runs=[](n=0)
  - ✅ **height**: img/2=31846 vs content=31850 tol=±956
  - ✅ **duplicate**: dup_run=10css px
  - ✅ **missing**: present=12 missing=0 of 12 欠落=[]
  - ✅ **ui_leak**: pink_px=0
  - ✅ **resolution**: img_w=2560 exp=2560(=1280x2)
  - ✅ **cleanup**: before=f6:s2:tag0:m0 after=f6:s2:tag0:m0
  - ✅ **errors**: our_errors=[] / page_noise=0件
  - ✅ **truth**: onscreen一致 worst=0.00 [(11147, 0.0), (19110, 0.0), (27072, 0.0)]

## 3. wiki_images — PASS
- カテゴリ: 3/10 画像・表が多い / 種別: live / 倍率: 2x
- 画像: 2560x30728px / 実測content=15677 scrollH=15364 capture=15364 / channel=
- 分割: split=True bands=18 attempts=1 trimmed=0px elapsed=6.6s
  - ✅ **blank**: runs=[](n=0)
  - ✅ **height**: img/2=15364 vs content=15677 tol=±470
  - ✅ **duplicate**: dup_run=0css px
  - ✅ **missing**: present=12 missing=0 of 12 欠落=[]
  - ✅ **ui_leak**: pink_px=0
  - ✅ **resolution**: img_w=2560 exp=2560(=1280x2)
  - ✅ **cleanup**: before=f6:s2:tag0:m0 after=f6:s2:tag0:m0
  - ✅ **errors**: our_errors=[] / page_noise=0件
  - ✅ **truth**: onscreen一致 worst=0.00 [(5377, 0.0), (9218, 0.0), (13059, 0.0)]

## 4. pythonorg — PASS
- カテゴリ: 実在サイト(一般) / 種別: live / 倍率: 2x
- 画像: 2560x4944px / 実測content=2472 scrollH=2472 capture=2472 / channel=
- 分割: split=False bands=1 attempts=1 trimmed=0px elapsed=1.8s
  - ✅ **blank**: runs=[](n=0)
  - ✅ **height**: img/2=2472 vs content=2472 tol=±74
  - ✅ **duplicate**: dup_run=0css px
  - ✅ **missing**: present=12 missing=0 of 12 欠落=[]
  - ✅ **ui_leak**: pink_px=0
  - ✅ **resolution**: img_w=2560 exp=2560(=1280x2)
  - ✅ **cleanup**: before=f4:s0:tag0:m0 after=f4:s0:tag0:m0
  - ✅ **errors**: our_errors=[] / page_noise=1件
  - ✅ **truth**: single-shot ≤16384px域(実証済のため無検査)

## 5. long — PASS
- カテゴリ: 2 縦20000px+(fixture) / 種別: fixture / 倍率: 2x
- 画像: 2560x45708px / 実測content=22855 scrollH=22871 capture=22871 / channel=
- 分割: split=True bands=26 attempts=1 trimmed=34px elapsed=7.9s
  - ✅ **blank**: runs=[](n=0)
  - ✅ **height**: img/2=22854 vs content=22855 tol=±686
  - ✅ **duplicate**: dup_run=0css px
  - ✅ **missing**: present=1 missing=0 of 1 欠落=[]
  - ✅ **ui_leak**: pink_px=0
  - ✅ **resolution**: img_w=2560 exp=2560(=1280x2)
  - ✅ **cleanup**: before=f4:s0:tag0:m0 after=f4:s0:tag0:m0
  - ✅ **errors**: our_errors=[] / page_noise=0件
  - ✅ **truth**: onscreen一致 worst=0.00 [(8004, 0.0), (13722, 0.0), (19440, 0.0)]

## 6. lazy — PASS
- カテゴリ: 3 遅延読込画像 / 種別: fixture / 倍率: 2x
- 画像: 2560x24120px / 実測content=12064 scrollH=12082 capture=12082 / channel=
- 分割: split=True bands=14 attempts=1 trimmed=44px elapsed=7.5s
  - ✅ **blank**: runs=[](n=0)
  - ✅ **height**: img/2=12060 vs content=12064 tol=±362
  - ✅ **duplicate**: dup_run=0css px
  - ✅ **missing**: present=12 missing=0 of 12 欠落=[]
  - ✅ **ui_leak**: pink_px=0
  - ✅ **resolution**: img_w=2560 exp=2560(=1280x2)
  - ✅ **cleanup**: before=f4:s0:tag0:m0 after=f4:s0:tag0:m0
  - ✅ **errors**: our_errors=[] / page_noise=0件
  - ✅ **truth**: onscreen一致 worst=0.00 [(4228, 0.0), (7249, 0.0), (10269, 0.0)]

## 7. fixedheader — PASS
- カテゴリ: 4 固定ヘッダー+追従 / 種別: fixture / 倍率: 2x
- 画像: 2560x8292px / 実測content=4145 scrollH=4161 capture=4161 / channel=
- 分割: split=False bands=1 attempts=1 trimmed=30px elapsed=2.0s
  - ✅ **blank**: runs=[](n=0)
  - ✅ **height**: img/2=4146 vs content=4145 tol=±124
  - ✅ **duplicate**: dup_run=0css px
  - ✅ **missing**: present=4 missing=0 of 4 欠落=[]
  - ✅ **ui_leak**: pink_px=0
  - ✅ **resolution**: img_w=2560 exp=2560(=1280x2)
  - ✅ **cleanup**: before=f6:s1:tag0:m0 after=f6:s1:tag0:m0
  - ✅ **errors**: our_errors=[] / page_noise=0件
  - ✅ **truth**: single-shot ≤16384px域(実証済のため無検査)

## 8. innerscroll — PASS
- カテゴリ: 5 内側スクロール / 種別: fixture / 倍率: 2x
- 画像: 2560x16272px / 実測content=8140 scrollH=8139 capture=8139 / channel=
- 分割: split=True bands=10 attempts=1 trimmed=6px elapsed=3.4s
  - ✅ **blank**: runs=[](n=0)
  - ✅ **height**: img/2=8136 vs content=8140 tol=±244
  - ✅ **duplicate**: dup_run=0css px
  - ✅ **missing**: present=1 missing=0 of 1 欠落=[]
  - ✅ **ui_leak**: pink_px=0
  - ✅ **resolution**: img_w=2560 exp=2560(=1280x2)
  - ✅ **cleanup**: before=f4:s0:tag0:m0 after=f4:s0:tag0:m0
  - ✅ **errors**: our_errors=[] / page_noise=0件
  - ✅ **truth**: onscreen一致 worst=0.00 [(2848, 0.0), (4883, 0.0), (6918, 0.0)]

## 9. infinite — PASS
- カテゴリ: 6 無限スクロール(打切) / 種別: fixture / 倍率: 2x
- 画像: 2560x46500px / 実測content=23251 scrollH=23250 capture=23250 / channel=
- 分割: split=True bands=26 attempts=1 trimmed=0px elapsed=7.8s
  - ✅ **blank**: runs=[](n=0)
  - ✅ **height**: img/2=23250 vs content=23251 tol=±698
  - ✅ **duplicate**: dup_run=0css px
  - ✅ **missing**: present=12 missing=0 of 12 欠落=[]
  - ✅ **ui_leak**: pink_px=0
  - ✅ **resolution**: img_w=2560 exp=2560(=1280x2)
  - ✅ **cleanup**: before=f4:s0:tag0:m0 after=f4:s0:tag0:m0
  - ✅ **errors**: our_errors=[] / page_noise=0件
  - ✅ **truth**: onscreen一致 worst=0.00 [(8137, 0.0), (13950, 0.0), (19762, 0.0)]

## 10. short — PASS
- カテゴリ: 7 短い1画面 / 種別: fixture / 倍率: 2x
- 画像: 2560x464px / 実測content=231 scrollH=900 capture=331 / channel=
- 分割: split=False bands=1 attempts=1 trimmed=198px elapsed=0.6s
  - ✅ **blank**: runs=[](n=0)
  - ✅ **height**: img/2=232 vs content=231 tol=±16
  - ✅ **duplicate**: dup_run=0css px
  - ✅ **missing**: present=3 missing=0 of 3 欠落=[]
  - ✅ **ui_leak**: pink_px=0
  - ✅ **resolution**: img_w=2560 exp=2560(=1280x2)
  - ✅ **cleanup**: before=f4:s0:tag0:m0 after=f4:s0:tag0:m0
  - ✅ **errors**: our_errors=[] / page_noise=0件
  - ✅ **truth**: single-shot ≤16384px域(実証済のため無検査)

## 11. wide — PASS
- カテゴリ: 8 横スクロール / 種別: fixture / 倍率: 2x
- 画像: 8700x3012px / 実測content=1507 scrollH=1506 capture=1506 / channel=
- 分割: split=False bands=1 attempts=1 trimmed=0px elapsed=1.9s
  - ✅ **blank**: runs=[](n=0)
  - ✅ **height**: img/2=1506 vs content=1507 tol=±45
  - ✅ **duplicate**: dup_run=12css px
  - ✅ **missing**: present=12 missing=0 of 12 欠落=[]
  - ✅ **ui_leak**: pink_px=0
  - ✅ **resolution**: img_w=8700 exp=8700(=4350x2)
  - ✅ **cleanup**: before=f4:s0:tag0:m0 after=f4:s0:tag0:m0
  - ✅ **errors**: our_errors=[] / page_noise=0件
  - ✅ **truth**: single-shot ≤16384px域(実証済のため無検査)

## 12. japanese — PASS
- カテゴリ: 9 日本語フォント / 種別: fixture / 倍率: 3x
- 画像: 3840x29397px / 実測content=9803 scrollH=9820 capture=9820 / channel=
- 分割: split=True bands=11 attempts=1 trimmed=63px elapsed=6.1s
  - ✅ **blank**: runs=[](n=0)
  - ✅ **height**: img/3=9799 vs content=9803 tol=±294
  - ✅ **duplicate**: dup_run=0css px
  - ✅ **missing**: present=1 missing=0 of 1 欠落=[]
  - ✅ **ui_leak**: pink_px=0
  - ✅ **resolution**: img_w=3840 exp=3840(=1280x3)
  - ✅ **cleanup**: before=f4:s0:tag0:m0 after=f4:s0:tag0:m0
  - ✅ **errors**: our_errors=[] / page_noise=0件
  - ✅ **truth**: onscreen一致 worst=0.00 [(3437, 0.0), (5892, 0.0), (8347, 0.0)]

## 13. tables — PASS
- カテゴリ: 10 テーブル多数 / 種別: fixture / 倍率: 2x
- 画像: 2560x11880px / 実測content=5937 scrollH=5954 capture=5954 / channel=
- 分割: split=False bands=1 attempts=1 trimmed=28px elapsed=2.3s
  - ✅ **blank**: runs=[](n=0)
  - ✅ **height**: img/2=5940 vs content=5937 tol=±178
  - ✅ **duplicate**: dup_run=11css px
  - ✅ **missing**: present=12 missing=0 of 12 欠落=[]
  - ✅ **ui_leak**: pink_px=0
  - ✅ **resolution**: img_w=2560 exp=2560(=1280x2)
  - ✅ **cleanup**: before=f4:s0:tag0:m0 after=f4:s0:tag0:m0
  - ✅ **errors**: our_errors=[] / page_noise=0件
  - ✅ **truth**: single-shot ≤16384px域(実証済のため無検査)

## 14. iframe — PASS
- カテゴリ: 11 iframe / 種別: fixture / 倍率: 2x
- 画像: 2560x5566px / 実測content=2783 scrollH=2798 capture=2798 / channel=
- 分割: split=False bands=1 attempts=1 trimmed=30px elapsed=1.4s
  - ✅ **blank**: runs=[](n=0)
  - ✅ **height**: img/2=2783 vs content=2783 tol=±83
  - ✅ **duplicate**: dup_run=26css px
  - ✅ **missing**: present=1 missing=0 of 1 欠落=[]
  - ✅ **ui_leak**: pink_px=0
  - ✅ **resolution**: img_w=2560 exp=2560(=1280x2)
  - ✅ **cleanup**: before=f4:s0:tag0:m0 after=f4:s0:tag0:m0
  - ✅ **errors**: our_errors=[] / page_noise=0件
  - ✅ **truth**: single-shot ≤16384px域(実証済のため無検査)

## 15. dark — PASS
- カテゴリ: 12 ダークテーマ / 種別: fixture / 倍率: 2x
- 画像: 2560x12718px / 実測content=6358 scrollH=6374 capture=6374 / channel=
- 分割: split=False bands=1 attempts=1 trimmed=30px elapsed=2.6s
  - ✅ **blank**: runs=[](n=0)
  - ✅ **height**: img/2=6359 vs content=6358 tol=±191
  - ✅ **duplicate**: dup_run=0css px
  - ✅ **missing**: present=1 missing=0 of 1 欠落=[]
  - ✅ **ui_leak**: pink_px=0
  - ✅ **resolution**: img_w=2560 exp=2560(=1280x2)
  - ✅ **cleanup**: before=f4:s0:tag0:m0 after=f4:s0:tag0:m0
  - ✅ **errors**: our_errors=[] / page_noise=0件
  - ✅ **truth**: single-shot ≤16384px域(実証済のため無検査)
