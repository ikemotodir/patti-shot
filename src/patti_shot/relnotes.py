"""Release notes generation (called by release.bat so the batch stays ASCII)."""
from __future__ import annotations

from . import __version__

NOTES = """PATTI SHOT v{ver}（Windows用・無料）

Webページを、スクロールしないと見えない一番下まで丸ごと1枚に撮影して PNG / PDF で保存するツールです。

## 使い方
1. 下の Assets から `PATTI_SHOT.exe` をダウンロード
2. ダブルクリックで起動（専用のブラウザが開きます）
3. 撮りたいページで右下のピンクの「PATTI SHOT」ボタンをクリック

※「WindowsによってPCが保護されました」と出たら「詳細情報」→「実行」。
署名のない個人開発アプリで必ず出る表示で、異常ではありません。

詳しくは: https://ikemotodir.github.io/patti-shot/

## このバージョンの変更点（v4.2.2）
- **起動したら真っ白なページが出ることがある不具合を修正しました**
  クリップボードにURL以外の文字（メモやコピーしたテキスト）が入っていると、
  それをURLと勘違いして開こうとし、失敗して空白ページのままになっていました。
  URLの判定を厳しくし、さらに読み込みに失敗しても必ず通常のページを開くようにしました。

## v4.2.1 の変更点
- **黒いコンソール画面が出なくなりました**（起動時に残っていた黒い窓を廃止）
- **ピンクの「PATTI SHOT」ボタンが必ず画面内に出るようになりました**
  （ウィンドウが画面より大きいとボタンが画面外にはみ出していたのを修正。起動時に最大化します）
- **キーボードで撮影できます**：`Ctrl+Shift+S`（または `Alt+S`）。ボタンを探さなくてもOK
- ページ側の作りでボタンが消えてしまう場合も、自動で出し直すようになりました

## v4.2.0 の変更点
**「いま見ているページ」をすぐ開けるようになりました**（URLのコピペ不要）。

- **1クリック連携**：設定（⚙）の「🔗 普段のブラウザから1クリックで開く設定」を押すと、
  普段のChromeのブックマークバーに置ける「PATTI SHOTで撮る」ボタンを用意します。
  撮りたいページでそれを押すだけで、そのページがPATTI SHOTで開きます
- **クリップボード連携**：普段のブラウザで Ctrl+L → Ctrl+C（URLをコピー）してから
  PATTI SHOT を開くと、そのページが自動で開きます（設定不要）
- 二重起動しなくなりました。すでに開いているときは新しいタブとして開きます

※ Chromeのセキュリティ仕様により、すでに開いている「普段のChromeのウィンドウ」を
　直接撮影することはできません（外部プログラムからの接続をChromeが禁止しているため）。
　PATTI SHOTのウィンドウはログイン状態を記憶するので、一度ログインすれば次回からそのままです。
"""


def write_notes(path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(NOTES.format(ver=__version__))


if __name__ == "__main__":
    import sys
    write_notes(sys.argv[1] if len(sys.argv) > 1 else "build/notes.md")
