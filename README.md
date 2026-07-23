# PATTI SHOT

STUDIO PATTI が作る、Windows 用の無料フルページ・スクリーンショットツール。
いま見ているWebページを、スクロールしないと見えない一番下まで **丸ごと1枚** の
PNG / PDF に保存します。

- **配布ページ（使い方はこちら）**: https://ikemotodir.github.io/patti-shot/
- **ダウンロード**: [最新版 PATTI_SHOT.exe](https://github.com/ikemotodir/patti-shot/releases/latest/download/PATTI_SHOT.exe)
- 利用者が触るのは `PATTI_SHOT.exe` の1ファイルだけ。撮りたいページで右下のピンクの
  **PATTI SHOT** ボタンを押すだけです。

> v4.0 から Windows 単体アプリになりました（旧Chrome拡張版は廃止）。

---

## リポジトリ構成（開発者向け）

| 場所 | 内容 |
|---|---|
| `src/patti_shot/` | アプリ本体（Python + Playwright, `channel="chrome"`） |
| `test/` | 自動検証ハーネス（`harness.py`）と各種検証。結果は `test/REPORT.md` |
| `build/build.bat` | PyInstaller で `PATTI_SHOT.exe` を生成 |
| `release.bat` | ビルド → GitHub Release 作成まで全自動（gh CLI） |
| `docs/` | 配布ページ（GitHub Pages で `/patti-shot/` として公開） |
| `CLAUDE.md` | 開発引き継ぎメモ（現在のPHASE・注意点・次にやること） |
| `PATTI_SHOT_v4_指示書.md` | 本プロジェクトの開発指示書 |

### 開発環境の準備

```
python -m venv .venv
.venv\Scripts\python -m pip install playwright pillow numpy img2pdf pyinstaller
.venv\Scripts\python -m playwright install chromium
```

検証（テスト用に `pymupdf` `psutil` も必要）:

```
.venv\Scripts\python test\harness.py
```

### リリース手順（ボス用・これだけ）

1. `src\patti_shot\__init__.py` の `__version__` を上げる
2. `release.bat` をダブルクリック（ビルド → GitHub Release 作成まで全自動）

---

## 既知の注意点

- 署名のないexeのため、初回実行時に SmartScreen 警告が出ます（「詳細情報」→「実行」）
- ウイルス対策ソフトが誤検知する可能性があります（PyInstaller製exeで起こり得ます）
- Windows専用（Windows 10 / 11）。macOS対応は範囲外
- Chrome がインストールされていない環境では、初回のみブラウザの自動取得が発生します
- 撮影・保存はすべて利用者のPC内で完結し、外部送信しません（通信は起動時の更新チェックのみ）

---

制作: 合同会社スタジオパッチ（愛知県一宮市） / STUDIO PATTI
