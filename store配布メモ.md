# store配布メモ ── Avast誤検知報告（False Positive報告）

> PATTI SHOT v4.1 改修指示書 §5 の準備物一式。
> 提出はボスの操作が必要（Avastのフォームは人間の送信が前提のため）。**全部コピペで済む状態**にしてある。

---

## なぜやるか

このPCのAvastが `PATTI_SHOT.exe` の起動を遮断した実績がある（ハッシュ同一のローカルビルドも遮断）。
PyInstaller製の署名なしexeは誤検知されやすい。Avastに「これは誤検知だ」と正式報告すると、
検体が解析されてホワイトリスト化され、**全世界のAvastユーザーの誤検知が解消**される可能性がある。

## 提出先

- **Avast誤検知報告フォーム**: https://www.avast.com/false-positive-file-form.php
  （「Report a file or website that is wrongly detected」のFile用フォーム）

## 提出するファイル

- `PATTI_SHOT.exe`（最新リリース）
- 手元に無い場合のダウンロード元: https://github.com/ikemotodir/patti-shot/releases/latest/download/PATTI_SHOT.exe
  ※Avastが起動を遮断してもファイル自体は提出できる（実行はしない）
  ※フォームのファイル上限（一般に~50MB）を超える場合は「File download URL」欄に上記URLを貼る方式でOK

## フォーム記入内容（コピペ用・英語）

| フォームの欄 | 入れる内容 |
|---|---|
| What would you like to report? | **False positive (file)** を選択 |
| File upload / File URL | `PATTI_SHOT.exe` を添付、またはURL欄に上のReleases URLを貼る |
| Detection name | Avastの警告画面に出た検出名（例: `Win64:Malware-gen` 等）。控えが無ければ空欄でも可 |
| Email | mm.arrowz.39@gmail.com |
| Description | 下の英文をコピペ |

**Description欄にコピペする英文:**

```
PATTI SHOT is a free, open-source full-page screenshot tool for Windows,
developed and distributed by STUDIO PATTI LLC (Japan).

- Official distribution page: https://ikemotodir.github.io/patti-shot/
- Full source code (public): https://github.com/ikemotodir/patti-shot
- Release file: https://github.com/ikemotodir/patti-shot/releases/latest/download/PATTI_SHOT.exe

The app is built with Python + PyInstaller (unsigned, individual developer),
which we believe triggers the false positive. The app:
- performs no data exfiltration (screenshots are saved locally only),
- makes network requests only to github.com to check for updates,
- contains no obfuscated or packed third-party payloads.

Avast currently blocks the executable from launching ("Access is denied"),
including locally built binaries with identical source. We kindly ask you to
analyze the file and whitelist it. Thank you.
```

## ボスの操作手順（1クリック単位）

1. https://www.avast.com/false-positive-file-form.php をブラウザで開く
2. 「False positive (file)」を選ぶ
3. 「ファイルを選択」→ `Downloads` 等にある `PATTI_SHOT.exe` を選ぶ
   （無ければ先に上のReleases URLからダウンロード。**実行はしなくていい**）
4. Email欄に `mm.arrowz.39@gmail.com` を入力
5. Description欄に上の英文ブロックを貼り付け
6. （出てくれば）reCAPTCHAのチェックを入れる
7. 「Submit」をクリック → 完了。返信メールが来ることがあるので受信箱を見ておく

## 提出後

- 数日〜2週間で解析される（返信が来ない場合もあるが、静かにホワイトリスト化されることが多い）
- 解消確認: Avast定義更新後に `PATTI_SHOT.exe` を再ダウンロード→起動できればOK
- **将来リリースのたびにexeのハッシュが変わる**ため、再発したら同じ手順で再提出（このメモを使い回す）
- 恒久対策の本命はコード署名証明書（EV/OV）だが、費用対効果は要検討。他社AVへの申請は今回やらない（指示書 §5）

---

📸 PATTI SHOT ── 制作: STUDIO PATTI LLC（合同会社スタジオパッチ・愛知県一宮市）
