# SST 音源選択およびメタデータ・タグ付けルール

このドキュメントは、Steam Soundtrack Tagger (SST) における音源ファイルの選択、ティア分類、およびメタデータ・タグ付けの正式なロジックを定義します。

## 1. ファイル選択とティア・ロジック

SST は、Steam のサウンドトラック・ディレクトリで見つかったオーディオ・ファイルを論理トラックごとにグループ化し、利用可能な最高品質のバージョンを採用します。

### 1.1 品質ティア (Quality Tiers)
- **Lossless (ティア 1)**: FLAC, WAV, AIFF, ALAC
- **Lossy High (ティア 2)**: OGG, AAC, M4A
- **MP3 (ティア 3)**: 標準的な MP3 ファイル

### 1.2 重複排除ロジック
ファイル名から品質・フォーマットを示す接尾辞（例：`(AIFF)`, `[FLAC]`, `(MP3)`）を削除して比較し、同一トラックとして統合します。複数のフォーマットが存在する場合、最高品質のティアが優先されます。

## 2. メタデータ同定ロジック

### 2.1 3層 API 統合
LLM 推論に頼る前に、以下の 3 つの構造化データソースを使用します：
1. **階層1 (公式 Store API)**: 日本語の基礎情報（名称、ジャンル）。
2. **階層2 (PICS Bridge)**: Steam 内部 DB から取得した正確なトラックリストとクレジット。
3. **階層3 (Steam Web API)**: 公式のユーザー定義人気タグ。

### 2.2 MusicBrainz 候補のランク付け
物理的な証拠に基づいてスコアリングされます：
- **AppID 一致 (+500点)**: MusicBrainz 内に Steam AppID への直接リンクがある。
- **SteamDB 一致 (+500点)**: MusicBrainz 内に SteamDB への直接リンクがある。
- **親 AppID 一致 (+300点)**: 親ゲームへのリンクがある。
- **構造の一致 (+50点)**: トラック数の完全一致。
- **トラックリスト指紋 (+200点)**: 曲名の平均類似度が 80% 超。

### 2.3 決定論的ファストトラック
直接リンクがあり、かつ「MBZ・Steam PICS・ローカル」の曲数が完璧に一致する場合、LLM をバイパスして自動的に `ARCHIVE` 判定を下します。

## 3. ID3v2.3 タグ付け標準

DJ機材や Windows との最大互換性を確保するため、以下の標準を適用します。

### 3.1 フィールド・マッピングとフォーマット
| ID3 フレーム | フィールド | フォーマット / ルール |
| :--- | :--- | :--- |
| **TIT2** | 曲名 | 統合された曲名。 |
| **TPE1** | アーティスト | MBZ または Steam からの主要作曲家・演奏者。 |
| **TALB** | アルバム名 | Steam 公式タイトル（Locked）。 |
| **TPE2** | アルバムアーティスト | `[開発元], [パブリッシャー]` |
| **TCON** | ジャンル | 接頭辞: `STEAM VGM, [全ジャンル]` |
| **TPUB** | レーベル | 公式 PICS レーベル または MBZ レーベル。 |
| **TYER** | 年 | 発売年 (YYYY)。 *注: MP3 は v2.3 のため TYER を使用。* |
| **TRCK** | トラック番号 | 単一の整数 (例: `1`, `16`)。 |
| **TPOS** | ディスク番号 | `n/N` 形式 (例: `1/1`)。 |
| **TIT1** | グルーピング | `[ゲーム名], Steam` |
| **COMM** | コメント | `[ゲーム名], [タグ], [AppID], [ストア URL]` |
| **TLAN** | 言語 | ISO 639-2 コード (例: `jpn`) |

### 3.2 技術的要件
- **厳格な ID3v2.3**: MP3 ファイルは強制的に v2.3 フォーマットで保存されます。
- **コメント欄の自動調整**: `COMM` フィールドが ID3v2.3 の制限（約2000文字）を超える場合、タグを末尾から一つずつ削除して収まるように自動調整します。

## 4. 振り分けとバリデーション (Archive vs. Review)

### 4.1 Archive (承認)
以下の条件をすべて満たす必要があります：
- LLM 自信度スコアが **100**（またはファストトラック適用）。
- 整合性品質 (Integrity Quality) が **95点以上**。
- "Dirty Tags"（曲名への番号混入）が存在しない。

### 4.2 Review (要確認)
以下の場合に `review/` へ送られます：
- 同定確信度が 100 未満、または品質が 95 未満。
- 音声変換エラー、または FFmpeg 警告が発生。
- LLM により人間による確認が推奨された。

---

# SST Audio Selection and Metadata Tagging Rules

This document defines the authoritative logic for audio file selection, tier classification, and metadata tagging for the Steam Soundtrack Tagger (SST).

## 1. File Selection & Tier Logic

SST groups audio files found in a Steam soundtrack directory by their logical tracks and adopts the highest quality version available.

### 1.1 Quality Tiers
- **Lossless (Tier 1)**: FLAC, WAV, AIFF, ALAC.
- **Lossy High (Tier 2)**: OGG, AAC, M4A.
- **MP3 (Tier 3)**: Standard MP3 files.

### 1.2 Deduplication Logic
The system collapse duplicates by stripping common quality suffixes (e.g., `(AIFF)`, `[FLAC]`, `(MP3)`) from filename stems. If multiple formats exist for the same track, the format with the highest tier is chosen.

## 2. Metadata Identification Logic

### 2.1 3-Tier API Consolidation
The system uses three structured data sources before resorting to LLM reasoning:
1. **Tier 1 (Official Store API)**: Basic localized info (Name, Genre).
2. **Tier 2 (PICS Bridge)**: Structured Tracklists and Credits directly from Steam's database.
3. **Tier 3 (Steam Web API)**: User-defined popular tags.

### 2.2 MusicBrainz Candidate Ranking
MBZ candidates are scored based on physical evidence:
- **AppID Match (+500)**: Direct Steam AppID link in `url-rels`.
- **SteamDB Match (+500)**: Direct SteamDB link for the AppID in `url-rels`.
- **Parent AppID Match (+300)**: Link to the parent game AppID in `url-rels`.
- **Structural Alignment (+50)**: Exact track count match.
- **Tracklist Fingerprint (+200)**: Average title similarity > 80%.

### 2.3 Deterministic Fast-Track
If a **Direct Link** is found and the **Track Count** matches perfectly across MBZ, Steam PICS, and Local files, the system promotes the album to `ARCHIVE` automatically, bypassing the LLM.

## 3. ID3v2.3 Tagging Standards

To ensure maximum compatibility with hardware (e.g., DJ gear) and Windows, the following standards are enforced.

### 3.1 Field Mapping & Formats
| ID3 Frame | Field | Format / Rule |
| :--- | :--- | :--- |
| **TIT2** | Title | Consolidated track title. No "Unknown". |
| **TPE1** | Artist | Main composers/performers from MBZ or Steam. |
| **TALB** | Album | Official Steam album title (Locked). |
| **TPE2** | Album Artist | `[Developer], [Publisher]`. |
| **TCON** | Genre | Prefixed: `STEAM VGM, [All Genres]`. |
| **TPUB** | Label | Official PICS Label or MBZ Label. |
| **TYER** | Year | Release Year (YYYY). *Note: MP3 uses TYER for v2.3.* |
| **TRCK** | Track Number | Single integer (e.g., `1`, `16`). |
| **TPOS** | Disc Number | `n/N` format (e.g., `1/1`). |
| **TIT1** | Grouping | `[Game Name], Steam`. |
| **COMM** | Comment | `[Game Name], [Tags], [AppID], [Store URL]`. |
| **TLAN** | Language | ISO 639-2 code (e.g., `jpn`). |

### 3.2 Technical Requirements
- **Strict ID3v2.3**: MP3 files are force-saved in v2.3 format.
- **Comment Pruning**: Tags in the `COMM` field are automatically removed from the end if the total length exceeds ~2000 characters to prevent ID3v2.3 limit violations.

## 4. Routing & Validation (Archive vs. Review)

### 4.1 Archive (Success)
Albums reach `archive/` only if:
- LLM confidence score is **100** (or Fast-Tracked).
- Integrity Quality is **95 or higher**.
- No "Dirty Tags" (track numbers mixed into titles) exist.

### 4.2 Review (Manual Check)
Albums are moved to `review/` if:
- Any doubt in identity (Score < 100) or quality (Quality < 95).
- Audio failures or FFmpeg warnings are detected.
- User review is manually requested by the LLM.
