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
"""


def write_notes(path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(NOTES.format(ver=__version__))


if __name__ == "__main__":
    import sys
    write_notes(sys.argv[1] if len(sys.argv) > 1 else "build/notes.md")
