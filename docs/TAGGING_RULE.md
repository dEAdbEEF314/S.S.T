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

| ID3 フレーム | フィールド | 内容 / フォーマットルール |
| :--- | :--- | :--- |
| **TIT2** | 曲名 | LLM によりクリーニングされた純粋な曲名。 |
| **TPE1** | アーティスト | MusicBrainz のクレジット（最優先）または Steam 開発元。 |
| **TALB** | アルバム名 | Steam 公式タイトル（不変）。 |
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
| **Tier 1** | **Lossless** | FLAC, WAV, AIFF, ALAC | **AIFF (.aif)** |
| **Tier 2** | **Lossy High** | OGG, AAC, M4A | **MP3 (.mp3)** |
| **Tier 3** | **Standard** | MP3 | **MP3 (.mp3)** |

### 1.1 Deduplication Logic
The system merges tracks by stripping quality tags like `(AIFF)` or `[FLAC]` from filenames. If multiple formats exist for the same track, the highest tier is prioritized.

---

## 2. ID3v2.3 Tagging Standard

To ensure maximum compatibility with DJ hardware and Windows Explorer, the **ID3v2.3** standard is strictly enforced.

| ID3 Frame | Field | Content / Format Rule |
| :--- | :--- | :--- |
| **TIT2** | Title | Pure track title cleaned by LLM. |
| **TPE1** | Artist | MusicBrainz credits (priority) or Steam developer. |
| **TALB** | Album | Official Steam title (Locked). |
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

- **Separators**:
  - General multi-value fields: `, ` (Comma + Space)
  - Community tags in `COMM`: `/ ` (Slash + Space)
- **Dynamic Size Adjustment**:
  - If the `COMM` field exceeds ~2000 bytes, community tags are **pruned from the end one-by-one** to fit within the limit.
