# PATTI SHOT v4.0 — CLAUDE.md（作業引き継ぎ）

STUDIO PATTI / 発注: 池本将（最終Yes-No権限者）。表記は必ず `PATTI` / `STUDIO PATTI`（`PATCH`表記は禁止）。
指示書: リポジトリ直下の [PATTI_SHOT_v4_指示書.md](PATTI_SHOT_v4_指示書.md)

## ツール概要
FireShot相当のフルページSSツールを **Windows単体exe**（Python + Playwright, `channel="chrome"`）として作り直す。
旧 `apps/patti-shot-main`（Chrome拡張）は方針転換で廃止・参照のみ。配布は `ikemotodir.github.io/patti-shot/`。

## 現在のPHASE
- PHASE 1（撮影エンジン＋自動検証ハーネス）完了。15件×9判定PASS（`test/REPORT.md`）。
- PHASE 2（フローティングUI / PNG・PDF出力 / 保存処理 / exe化）完了。完了条件1〜8 PASS。exe自己テスト（`PATTI_SHOT_SELFTEST=<url>`）で実Chrome起動→撮影→PNG/PDF保存まで実証。
- **PHASE 3（自動更新 / release.bat / 配布ページ / 棚トップ更新）完了・池本確認待ち。** v4.0.1公開済み（https://github.com/ikemotodir/patti-shot/releases ）。配布ページ https://ikemotodir.github.io/patti-shot/ 稼働・棚トップのカードも「公開中」化済み。配布ページは`docs/`（GitHub Pagesの制約でspecの`site/`は`docs/`に読み替え）。

## PHASE 3の要点・ハマりどころ
- **SSL**: Python3.13+の`VERIFY_X509_STRICT`が、セキュリティソフトのHTTPS検査CA（basicConstraints非critical）を拒否→更新チェックが黙って失敗する。`update._ssl_context()`でstrictのみ解除（チェーン検証は維持）。v4.0.0はこの修正前のexeだったためリリース削除→v4.0.1で置換済み。
- **updater.bat**: `timeout.exe`はコンソール無しプロセスで即エラーになる（リトライが一瞬で溶ける）→ `ping -n 2`で待機。DLファイルのAVスキャンロック対策でdelもリトライ。パスは引数渡し（bat本体はASCII維持）。ユニーク名で生成。
- **Avast（このPC）**: 池本が`build\dist\PATTI_SHOT.exe`を**ファイル例外**登録済み。ただし例外は**ファイル単位で、置き換え直後の“新しく書かれたexe”の起動は一時的に遮断される**（実時間スキャン）。数十秒後や内容不変なら起動可。→ **推奨は「フォルダ例外」**（build\dist配下やDownloads\PATTI SHOTごと）にして置き換え後も許可されるようにすること。
- gh CLIは導入済み・`ikemotodir`で認証済み。release.batはv4.0.1/v4.1.0を全自動公開済み（重複タグ拒否ガード付き）。

## 自動更新（条件9）実戦検証の結論（2026-07-23）
実物 v4.0.1 → v4.1.0 でE2E検証（`test/test_update_e2e_live.py`、Avast許可パス`build\dist\PATTI_SHOT.exe`上で実施）。安全装置は`test/test_update_safety.py`、UIは`test/test_update_ui.py`。
- **検知/DL/サイズ・ハッシュ/置き換え/更新後の撮影/ログイン(Cookie)維持/後始末/多重起動なし/最新版で誤検知なし= すべてPASS。**
- **自動再起動の根本原因を特定**：`start "" %1`自体は正しく再起動する（分離テストでPASS）。問題は**Avastが“置き換え直後のexe”の起動をスキャン中に遮断**すること。→ updater.batに**再起動前ウェイト`ping -n 8`（約7秒）を追加**（`update._UPDATER_BAT`）。この遅延で**遮断が解消（0秒=遮断、8秒/20秒=起動OK）を実測**。
- **注意（重要）**：この遅延は**新しいexe側のupdate.pyが書くbat**で効く。よって既存配布の v4.0.1 / v4.1.0（遅延追加前ビルド）は、更新自体は成功するが**再起動だけAvastに一時遮断される**（利用者はexeをもう一度開けば新版。中身は更新済み）。**次リリース以降**は自動再起動もAvast上で成立する見込み（実測ベース）。フォルダ例外にすればより確実。
- 池本のPCが更新テストの起点にできるのは`build\dist\PATTI_SHOT.exe`のみ（他パス/TEMPはAvast遮断）。

## PHASE 2の要点・ハマりどころ
- UI⇔Python連携は**binding不可**（sync Playwrightはbindingハンドラ内で長時間のネスト呼び出しができずデッドロック）。→ FABは`<html>`属性`data-patti-shot-request`に要求を書き、`app.run`のポーリングループが撮影を実行して`data-patti-shot-result`で返す方式。進捗は`document.title`（撮影に写らない）で表示。
- **メモリリーク（重要）**：撮影ごとに巨大配列を確保→解放するとPlaywrightの割当と断片化し解放領域が再利用されず、1回~90MB増加（Python3.14/numpy2.5.1）。→ `engine.capture(reuse_buffer=True)`で**出力バッファを使い回し**（アプリは撮影結果を即保存するので安全）。ただし複数結果を同時保持するテストは`reuse_buffer=False`（既定）で独立配列を使う。app.do_captureはTrue。連続10回で+119MB（合格域）。
- PNG復号は`np.array(im.convert("RGB"))`だとPIL/一時バッファがOSに返らず漏れる → numpy所有バッファへコピー（imaging.png_bytes_to_array）。
- exe化：`--collect-all playwright`でドライバ同梱。channel="chrome"利用のためChromium本体は非同梱（Chrome前提）。Chrome不在時は`browser._install_chromium()`で初回DL（**未検証**）。

## 環境（重要）
- Python 3.14.6 のみ。依存は `.venv`（`patti-shot/.venv`）に導入済（playwright 1.61 / pillow / numpy）。
- **ネットワークは PowerShell からのみ疎通。Bash(Git Bash) はネット遮断。** 撮影・検証は必ず PowerShell 経由で実行する。
- Chrome 導入済（`channel="chrome"`）。Chromium フォールバックも `playwright install chromium` 済。
- gh CLI 未導入（PHASE 3で必要）。

## 実行方法
```
# 自動検証ハーネス（全ページ）
.\.venv\Scripts\python.exe test\harness.py
# 一部だけ:  test\harness.py --only short,wide,dark
# 目視したいとき: --headed
```
結果は `test/REPORT.md`、失敗画像は `test/artifacts/*_FAIL.png`、各ページの縮小版は `*_thumb.png`。

## 設計の要点（指示書STEP2が本丸）
- `src/patti_shot/jslib.py`：STEP1前処理（スクロール主体特定・遅延読込発火・描画強制）とSTEP2「実コンテンツ高さ実測（scrollHeightを信用しない）」。全変更は復元レジストリで巻き戻す（後始末）。
- `src/patti_shot/engine.py`：撮影は2経路。(1)原則ワンショット＝CDP `captureScreenshot`（captureBeyondViewport, clip.scale, y=0起点）で高速・継ぎ目なし（Chromeは~63700デバイスpxまで一発OKを実測）。(2)それを超える巨大ページのみ区間分割＝固定/stickyを無害化→Emulationで倍率設定→各ビューポートをスクロールしてno-clip撮影→結合（**高オフセットclipはChromeの~16384px面制限で破綻するため、必ずスクロール+no-clip方式**）。空白検出時は倍率を下げて再撮影。末尾均一色トリム。
- `src/patti_shot/imaging.py`：空白帯/重複/欠落/UI写り込み判定・トリム・結合（Pillow/numpy）。
- `src/patti_shot/browser.py`：永続プロファイル起動（chrome優先→chromium）。
- `test/harness.py`：第6章の8判定を機械判定。`test/fixtures.py`＝再現可能なローカル雛形（構造カテゴリ網羅）、`test/jplatpat.py`＝J-PlatPat商標検索の自動化。

## 既知の注意点
- 極端に長いページ（3万px級）のワンショット撮影は Chrome のレンダリングで数十秒かかる（正常）。
- 空白帯判定はCSS px基準（300px×倍率）。倍率で誤検知しないよう実装済み。
- J-PlatPat は SPA。検索欄 `#t01_srchCondtn_mk_txtKeywd0` に語を入れ「検索」押下→結果ページ。到達不能時はハーネスが「未検証」と正直に記録（PASS偽装しない）。

## exe生成・動作確認
```
build\build.bat                                  # PATTI_SHOT.exe を生成
# 自己テスト（実Chrome起動→撮影→PNG/PDF保存を無人で検証）:
set PATTI_SHOT_SELFTEST=https://example.com/ && set PATTI_SHOT_OUT_DIR=%TEMP%\st && build\dist\PATTI_SHOT.exe
```
完了条件の機械検証：`test\test_output.py` / `test_app.py` / `test_split.py` / `test_conditions.py`。

## 次にやること
- 池本：Avastの例外登録（上記）→ 実機でexeダブルクリック→撮影→（次回リリース時）更新ボタンの体感確認。
- 次リリースの手順：`__version__`を上げて`release.bat`をダブルクリックするだけ。
- 残・未検証：条件9「再起動」の**実配布exeでのライブ通し**（現行v4.0.1/v4.1.0は遅延追加前のため。遅延の効果自体は実測済み・次リリースから成立見込み）。より確実にするなら**池本がAvastを“フォルダ例外”に変更**。Chromium自動DLフォールバック（Chrome不在環境なし）、PDF日本語可読性の最終目視。
