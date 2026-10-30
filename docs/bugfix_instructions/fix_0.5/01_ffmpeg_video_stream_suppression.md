# 修正指示書 01: FFmpeg 変換における映像ストリーム抑制 (-vn) によるクラッシュ防止

## 1. 背景と課題

AppID `2410560`（デイヴ・ザ・ダイバー Original Soundtrack）において、全92曲中91曲が正常に処理されたが、1曲（`81_Chasing Core.mp3`）で `FFmpeg failed with exit code 69` が発生し、`CRITICAL: Audio Source Error` として Review 送りとなった。

### 原因調査
元ファイル `81_Chasing Core.mp3` には `3000x3000` の高解像度 PNG アートワーク（attached pic）が埋め込まれていた。
`AudioTagger.convert_and_limit` の FFmpeg 呼び出しにおいて：
```python
cmd = ["ffmpeg", "-y", "-i", str(source_path)]
...
cmd += ["-codec:a", "libmp3lame", "-b:a", "320k", "-id3v2_version", "3"]
cmd.append(str(target_path))
```
ビデオストリーム（画像）を抑制するオプション（`-vn`）が指定されていなかったため、FFmpeg が入力の Video ストリームを MP3 出力コンテナへマッピングしようとしたが、`-codec:v` の指定やパケット送出が行われず、以下のエラーで終了コード 69 となった：
```
[mp3 @ 0x5f2d881eab00] No packets were sent for some of the attached pictures.
Conversion failed!
```

S.S.T では、アートワークの抽出・リサイズ・埋め込みは後段の `AudioTagger.write_tags`（mutagen）で安全かつ正式に行われるため、FFmpeg 側で画像ストリームをトランスコード・パススルーする必要は一切ない。

## 2. 解決方針

`AudioTagger.convert_and_limit` において、基本 FFmpeg コマンドに `-vn` を常時付与する。
これにより、入力ファイルにどのような形式・解像度のアートワーク画像ストリームが含まれていても、FFmpeg は純粋な音声ストリームのみを安全にトランスコードし、exit code 69 による変換失敗を根絶する。

## 3. 実装詳細

### `src/sst/tagger.py`

`AudioTagger.convert_and_limit` 内のコマンド構築部分を改修：

```python
# Basic command with -vn to discard embedded video/attached pictures (handled by mutagen in write_tags)
cmd = ["ffmpeg", "-y", "-i", str(source_path), "-vn"]
```

## 4. 安全境界

- 対象は FFmpeg による音声変換処理のみであり、ID3 タグ書き込み（mutagen による APIC フレーム付与）には一切影響を与えない。
- ロスレス変換（AIFF）およびロッシー変換（MP3）の双方が保護される。
