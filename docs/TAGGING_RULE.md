# S.S.T (Steam Soundtrack Tagger) タグ付け・品質基準

このドキュメントは、S.S.T における音源選択、ティア分類、および ID3v2.3 タグ付けの技術標準を定義します。

---

## 1. 音源ファイルの品質基準 (Quality Tiers)

S.S.T は論理トラックごとに最高品質のファイルを自動選択（Adopt）します。

| ティア | カテゴリ | フォーマット | 最終出力形式 |
| :--- | :--- | :--- | :--- |
| **ティア 1** | **Lossless** | FLAC, WAV, AIFF, ALAC | **AIFF (.aif)** |
| **ティア 2** | **Lossy High** | OGG, AAC, M4A | **MP3 (.mp3)** |
| **ティア 3** | **Standard** | MP3 | **MP3 (.mp3)** |

### 1.1 重複排除ロジック
ファイル名から `(AIFF)`, `[FLAC]` などの品質タグを除去して比較し、同一トラックとして統合します。複数のフォーマットが存在する場合、最高品質のティアが優先されます。

---

## 2. ID3v2.3 タグ付け標準

DJ機材および Windows エクスプローラーとの最大互換性を確保するため、**ID3v2.3** 規格を強制します。

*   **文字コード仕様**: ID3v2.3 規格は UTF-8 をサポートしていません。そのため、日本語や韓国語などの非アスキー文字を含むテキストフレーム（TIT2、TPE1、TALB、COMM等）を書き込む際は、すべて **UTF-16 with BOM (encoding=1)** を使用してエンコードします。


| ID3 フレーム | フィールド | 内容 / フォーマットルール |
| :--- | :--- | :--- |
| **TIT2** | 曲名 | **バイリンガル・タイトル (Plan B)**: `{Local} / {English}`<br>※MBZ/Steam/ローカル情報から構築。結合後 60文字を超える場合は `{Local}` のみを優先。 |
| **TPE1** | アーティスト | MusicBrainz クレジット（最優先）または Steam 開発元。 |
| **TALB** | アルバム名 | Steam 公式タイトルまたはバイリンガル・タイトル. |
| **TPE2** | アルバムアーティスト | `開発元, 出版社` |
| **TCON** | ジャンル | `STEAM VGM, [全ジャンル]` (カンマ区切り) |
| **TPUB** | レーベル | 公式 PICS レーベル、MBZ レーベル、または `開発元, 出版社` |
| **TYER** | 年 | 発売年 (YYYY)。*注: v2.3 のため TYER フレームを使用。* |
| **TRCK** | トラック番号 | 単一の整数。 |
| **TPOS** | ディスク番号 | `n/N` 形式 (例: `1/1`)。 |
| **TIT1** | グルーピング | `[親ゲーム名], Steam` |
| **COMM** | コメント | `親ゲーム名, [タグ1/ タグ2/ ...], AppID, ストア URL` |
| **TLAN** | 言語 | ISO 639-2 コード (例: `jpn`) |
| **APIC** | 埋め込み画像 | MusicBrainz または Steam ストアの Front Cover。 |

---

## 3. 実装要件

- **出力形式**: 
  - 最終成果物は `{SST_OUTPUT_DIR}/{archive | review}/{app_id}_{Album_name}.zip` の ZIP アーカイブとして保存されます。
  - `disc_{DiscNumber}/{filename}` は ZIP 内部の構成です。
- **レポート形式**:
  - 各アルバムの処理結果は、リッチな装飾を施した **HTML 形式 (`AUDIT_REPORT.html`)** で出力されます。従来の Markdown 形式は廃止またはこの HTML に統合されます。
- **セパレータ**:
  - 一般的な複数値フィールド: `, ` (カンマ＋スペース)
  - `COMM` タグ内のコミュニティタグ: `/ ` (スラッシュ＋スペース)
- **文字数制限の動的調整**:
  - `COMM` フィールドが約 2000バイトを超える場合、末尾から**タグ単位で自動削除**して制限内に収めます。

---

# S.S.T (Steam Soundtrack Tagger) Tagging & Quality Standards

This document defines the technical standards for audio selection, tier classification, and ID3v2.3 tagging within S.S.T.

---

## 1. Audio Quality Tiers

S.S.T automatically adopts the highest quality file for each logical track.

| Tier | Category | Input Formats | Final Output Format |
| :--- | :--- | :--- | :--- |
| **Tier 1** | **Lossless** | FLAC, WAV, AIFF, AIF, ALAC | **AIFF (.aif)** |
| **Tier 2** | **Lossy High** | OGG, AAC, M4A | **MP3 (.mp3)** |
| **Tier 3** | **Standard** | MP3 | **MP3 (.mp3)** |

### 1.05 Audio Downsampling & Resampling Limits
To ensure maximum compatibility with hardware media players (such as DJ CDJs) and prevent unnecessary file bloat:
* **Maximum Output Limits**: 24-bit / 48 kHz.
* **Conditional Downsampling**: Lossless source audio exceeding 24-bit depth or 48 kHz sampling rate (e.g. 24-bit/96kHz, 32-bit/192kHz) is dynamically downsampled to **24-bit / 48 kHz** during AIFF conversion using FFmpeg.
* **No Upsampling**: Source audio already below the limits (e.g. 16-bit / 44.1 kHz CD quality) **must not** be upsampled to 24-bit/48kHz. It is converted to AIFF while preserving its original sampling rate and bit depth.
### 1.1 Deduplication Logic & Tag Merging
The system identifies and groups identical logical tracks across multiple physical files using a hybrid mapping strategy:
1. **Track Number & Duration Matching**: Prioritizes mapping based on the track number. It extracts track numbers from the beginning of filenames, falling back to embedded metadata (`track_number` tag) if the filename lacks prefix numbers. If the duration difference is less than 1.0 second, they are merged.
2. **Fuzzy Name Matching**: Standardizes filenames by removing noise and album names, then groups files if the name similarity is >= 85% and the duration difference is < 1.0 second.
3. **Format Priority & Merging**: If multiple formats (variants) exist for the same track:
   - The final audio source is adopted based on the order defined in the `.env` variable `AUDIO_FORMAT_PRIORITY` (default: `flac,alac,aiff,wav,mp3,m4a,ogg`).
   - Metadata is merged across all variants in the priority order. Missing metadata in higher-priority formats (e.g. WAV having no tags) is automatically backfilled and merged from lower-priority formats (e.g. MP3) that contain embedded tags.

---

## 2. ID3v2.3 Tagging Standard

To ensure maximum compatibility with DJ hardware and Windows Explorer, the **ID3v2.3** standard is strictly enforced.

*   **Encoding Specification**: The ID3v2.3 standard does not support UTF-8. Therefore, all text frames containing non-ASCII characters (such as Japanese or Korean) like TIT2, TPE1, TALB, and COMM must be encoded using **UTF-16 with BOM (encoding=1)**.


| ID3 Frame | Field | Content / Format Rule |
| :--- | :--- | :--- |
| **TIT2** | Title | **Bilingual Title (Plan B)**: `{Local} / {English}`<br>Built from MBZ/Steam/local sources. If the combined title exceeds 60 characters, defaults to `{Local}` only. |
| **TPE1** | Artist | MusicBrainz credits (Priority) or Steam developer. |
| **TALB** | Album | Official Steam title or Bilingual Title. |
| **TPE2** | Album Artist | `Developer, Publisher` |
| **TCON** | Genre | `STEAM VGM, [All Genres]` (comma separated) |
| **TPUB** | Label | Official PICS Label, MBZ Label, or `Developer, Publisher`. |
| **TYER** | Year | Release Year (YYYY). *Note: Uses TYER frame for v2.3.* |
| **TRCK** | Track Number | Single integer. |
| **TPOS** | Disc Number | `n/N` format (e.g., `1/1`). |
| **TIT1** | Grouping | `[Parent Game Name], Steam` |
| **COMM** | Comment | `Parent Name, [tag1/ tag2/ ...], AppID, Store URL` |
| **TLAN** | Language | ISO 639-2 code (e.g., `jpn`) |
| **APIC** | Artwork | Embedded front cover from MusicBrainz or Steam. |

---

## 3. Implementation Requirements

- **Output Format**:
  - Final artifacts are preserved as ZIP archives: `{SST_OUTPUT_DIR}/{archive | review}/{app_id}_{Album_name}.zip`.
  - `disc_{DiscNumber}/{filename}` is the internal structure inside each ZIP.
- **Report Format**:
  - Processing results for each album are output in a rich **HTML format (`AUDIT_REPORT.html`)**. Legacy Markdown reports are deprecated or integrated into this HTML.
- **Separators**:
  - General multi-value fields: `, ` (Comma + Space)
  - Community tags in `COMM`: `/ ` (Slash + Space)
- **Dynamic Size Adjustment**:
  - If the `COMM` field exceeds ~2000 bytes, community tags are **pruned from the end one-by-one** to fit within the limit.
