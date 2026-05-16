# S.S.T (Steam Soundtrack Tagger) - 決定版仕様書

本書は S.S.T プロジェクトにおける**唯一の真実（Single Source of Truth）**です。過去のドキュメントはすべて非推奨となりました。本書は、システムの挙動、メタデータの整合性、および処理パイプラインに関する鉄の掟を定義します。

---

## 1. 根本原理: 「一度のアーカイブで、一生の信頼を」
- **主要ターゲット**: 日本語話者。
- **目標**: 高精度、メンテナンスフリーのオーディオアーカイブ。
- **ポリシー**: メタデータの正確性や音源の整合性に少しでも疑念がある場合、そのアイテムは必ず `REVIEW` へ送られなければならない。`ARCHIVE` ステータスは、100% の信頼性を象徴するものでなければならない。

---

## 2. メタデータの主権（確定情報：LOCKED TRUTH）
特定の情報は「決定論的（Deterministic）」と見なされ、LLM やヒューリスティックによって変更することはできない。

### 2.1 Steam API データ (LOCKED - 3層APIアーキテクチャ)
信頼性を最大化しつつスクレイピングを廃止するため、システムは3つのAPIを統合して情報を取得する：
- **階層1 (公式 Store API)**: 日本語のアルバム名、公式ジャンル、リリース日を取得。
- **階層2 (セルフホスト PICS Bridge)**: 構造化されたトラックリスト、多言語クレジット、レーベル情報を Steam 内部 DB (PICS) から直接取得。
- **階層3 (Steam Web API)**: 公式 Web API キーを使用して、高精度なユーザータグ（人気タグ）を取得。

これらのソースから得られる以下のフィールドは絶対的な真実である：
- **アルバムタイトル**: `steam_meta.name`
- **アーティスト (アルバムレベル)**: `steam_meta.developer`, `steam_meta.publisher`
- **リリース年**: `release_date` から正規表現で抽出した 4 桁の数値。
- **Steam ID**: `app_id`, `parent_app_id`
- **コメントメタデータ**: 親ゲームの詳細（名前、人気タグ、URL）を参照しなければならない。

### 2.2 ハイブリッド・スコアリング・判定システム
絶対的な信頼性を確保するため、システムは三段階の評価プロセスを採用する：

#### 第一段階：Python による数学的ふるい分け（`mbz.py` で計算）
- **AppID 一致 (+500点)**: `url-rels` 内に Steam AppID への直接リンクがある。
- **SteamDB 一致 (+500点)**: `url-rels` 内に SteamDB への直接リンクがある。
- **親ゲーム AppID 一致 (+300点)**: `url-rels` 内に親ゲーム AppID へのリンクがある。
- **Bandcamp ボーナス (+100点)**: `url-rels` 内に公式 Bandcamp リンクがある。
- **タイトル類似度 (0〜+100点)**: Steam 名またはローカルタグに対する最高の `SequenceMatcher` スコア。
- **構造の一致 (+50点)**: トラック数の完全一致（1曲の乖離につき10点を減点）。
- **トラックリストの指紋 (+200点)**: 各曲名の平均類似度が 80% を超える場合に付与。

#### 第二段階：LLM による意味論的監査（`llm.py` で計算）
LLM は、事前にソートされたショートリスト（上位 3〜5 件）に対して最終的な裁定を下す。

#### 第三段階：決定論的ファストトラック（LLM バイパス）
以下の条件を満たす場合、LLM への問い合わせを行わず自動的に `ARCHIVE` へ昇格させる：
1. MusicBrainz 内に **直接リンク**（Steam または SteamDB）が存在する。
2. **トラック数** が MBZ、PICS、ローカルファイル間で完璧に一致する。

### 2.3 ゲート方式スコアリングシステム
LLM の確信度スコアは、以下の厳格な閾値に従わなければならない：
- **Rank S (100%)**: Steam、MBZ、ローカルが完璧に一致。 -> **ARCHIVE**
- **Rank A (95%)**: 高い一貫性があり、"Dirty Tags" が存在しない。 -> **ARCHIVE**
- **Rank B (80-90%)**: わずかな不一致、曲数の相違、または "Dirty Tags" がある。 -> **REVIEW**
- **Rank C (< 80%)**: 競合がある、または証拠が不十分。 -> **REVIEW**

---

## 3. オーディオおよびパッケージングの整合性
### 3.1 ネイティブ・バッファリング戦略
Windows マウント経由の I/O ジッターを防ぎ、クリーンな出力を保証するため：
1.  **バッファ**: 音源を作業用 WSL2 バッファ（`/tmp/sst-work/buffer_*`）にコピーする。
2.  **変換**: ローカルで FFmpeg を実行する。**MP3 ファイルは機器互換性のために ID3v2.3 を強制**する。
3.  **検証**: FFmpeg の警告またはエラーは、**強制的に REVIEW** をトリガーする。

### 3.2 デプロイおよび展開
サントラは安全な転送のために一度 ZIP 化された後、Windows ホスト上で WSL から呼び出されたネイティブの `tar.exe` によって自動展開される。これにより、ファイルシステムの境界を越えて整合性が保たれる。

---

## 4. LLM 運用契約（ゼロ・ハルシネーション）
- **思考言語**: 日本語 (JA) のみ。
- **推論の禁止**: 内部的なファイル名から曲名やアーティストを推測することを禁ずる。
- **セマンティック・ラベリング**: Review アイテムに対して、LLM は具体的なデータ異常の内容を人間が読みやすいラベルで提供しなければならない。

---

## 5. タギングフォーマット標準
- **セパレータ**: 複数値フィールドには `, `（カンマ＋スペース）を使用する。
- **言語タグ (TLAN)**: ISO 639-2（例: `jpn`）を使用する。
- **フィールドマッピング**:
    - `TPE1` (アーティスト): MusicBrainz クレジット（最優先）または開発者（フォールバック）。
    - `TPE2` (アルバムアーティスト): 開発者, 出版社。
    - `TALB` (アルバム名): Steam アルバム名 (Locked)。
    - `TPUB` (レーベル): 公式 PICS レーベル または MBZ レーベル。フォールバックとして出版社。
    - `COMM` (コメント): [親ゲーム名], [人気タグ], [AppID], [ストア URL]。
      - *注*: ID3v2.3 の 2000 文字制限に収めるため、タグは末尾から自動的に切り詰められる。

---

## 6. システム実行モード
- **デフォルトモード**: `LOG_LEVEL=INFO`。標準的な追記型ログ。
- **デバッグモード (`--dev`)**: `LOG_LEVEL=DEBUG` を強制。実行ごとに一意のログファイルを生成し、エラー時の中間ファイルを保持する。
- **重要コマンド**: `--delete-db` および `--finalize` は、**3 段階の確認**を必須とする。

---

## 7. 設定 (`.env`)
究極データ取得モードに必要な変数：
- `STEAM_WEB_API_KEY`: 公式タグ取得用。
- `STEAM_LOGIN_SECURE`: `userdata.json` によるパーソナライズスキャン用。
- `STEAM_PICS_BRIDGE_URL`: ローカル Docker PICS ブリッジの URL。

---

# S.S.T (Steam Soundtrack Tagger) - The Definitive Specification

This is the **Single Source of Truth** for the S.S.T project. Any past documentation is deprecated. This document defines the ironclad rules for the system's behavior, metadata integrity, and processing pipeline.

---

## 1. Core Principle: "Archive once, trust forever"
- **Primary Audience**: Japanese speakers.
- **Goal**: High-precision, zero-maintenance audio archiving.
- **Policy**: If there is *any* doubt about metadata accuracy or audio integrity, the item MUST be sent to `REVIEW`. A status of `ARCHIVE` must represent 100% reliability.

---

## 2. Metadata Sovereignty (The "LOCKED TRUTH")
Specific information is considered "Deterministic" and cannot be modified by LLMs or heuristics.

### 2.1 Steam API Data (LOCKED - 3-Tier Architecture)
To maximize data depth while ensuring reliability, the system uses a 3-tier API fetch strategy (Zero Scraping):
- **Tier 1 (Official Store API)**: Retrieves localized Album Title, Genres, and Release Date.
- **Tier 2 (Self-hosted PICS Bridge)**: Retrieves structured Tracklists, multi-language Credits, and Label information directly from Steam's internal PICS database.
- **Tier 3 (Steam Web API)**: Retrieves high-fidelity User Tags (popular tags) using an official API key.

The following fields from these APIs are absolute truths:
- **Album Title**: `steam_meta.name`
- **Artist (Album-level)**: `steam_meta.developer`, `steam_meta.publisher`
- **Release Year**: Extracted via 4-digit regex from `steam_meta.release_date`.
- **Steam IDs**: `app_id`, `parent_app_id`
- **Comment Metadata**: Must reference the **Parent Game** details including its popular tags.

### 2.2 Hybrid Scoring & Decision System
To ensure absolute reliability, the system employs a three-stage evaluation process:

#### Stage 1: Python Mathematical Sieve (Calculated in `mbz.py`)
Python calculates a deterministic score for each MusicBrainz candidate based on physical evidence:
- **AppID Match (+500)**: Direct Steam AppID link in `url-rels`.
- **SteamDB Match (+500)**: Direct SteamDB link for the AppID in `url-rels`.
- **Parent AppID Match (+300)**: Link to the parent game AppID in `url-rels`.
- **Bandcamp Bonus (+100)**: Official Bandcamp link in `url-rels`.
- **Title Similarity (0 to +100)**: Highest `SequenceMatcher` score against Steam Name or Local Tags.
- **Structural Alignment (+50)**: Exact track count match. (Subtracts 10 per track discrepancy).
- **Tracklist Fingerprint (+200)**: Awarded if the average similarity of track titles exceeds 80%.

#### Stage 2: LLM Semantic Audit (Calculated in `llm.py`)
The LLM acts as the final arbiter on a pre-sorted shortlist (Top 3-5 candidates):
- **Translation Matching**: Resolves linguistic differences (e.g., "Battle" vs "戦闘").
- **Tag Hygiene**: Identifies "Dirty Tags" or other subtle anomalies.
- **Final Judgment**: Assigns the final rank (S, A, B, or C).

#### Stage 3: Deterministic Fast-Track (LLM Bypass)
The system automatically promotes an album to `ARCHIVE` without an LLM query if:
1. A **Direct Link** (Steam or SteamDB) is found in MusicBrainz.
2. The **Track Count** matches perfectly across MBZ, PICS, and Local files.

### 2.3 Gate-based Scoring System
LLM confidence scores must adhere to a strict threshold:
- **Rank S (100%)**: Perfect match between Steam, MBZ, and Local Tags. -> **ARCHIVE**
- **Rank A (95%)**: High consistency, no "Dirty Tags". -> **ARCHIVE**
- **Rank B (80-90%)**: Any minor discrepancy, track count mismatch, or "Dirty Tags". -> **REVIEW**
- **Rank C (< 80%)**: Conflict or insufficient evidence. -> **REVIEW**

---

## 3. Audio & Packaging Integrity
### 3.1 Native Buffering Strategy
To prevent I/O jitter and ensure clean output:
1.  **Buffer**: Copy raw source files to a dedicated WSL2 buffer (`/tmp/sst-work/buffer_*`) outside the output tree.
2.  **Transform**: Execute FFmpeg locally. **MP3 files are strictly forced to ID3v2.3** for hardware compatibility.
3.  **Validate**: Any FFmpeg warning/error triggers **Forced REVIEW**.

### 3.2 Deployment & Extraction
Soundtracks are first packaged as ZIPs for safe transfer, then automatically extracted on the Windows host using native `tar.exe` called from WSL. This preserves file integrity across filesystems.

---

## 4. LLM Operational Contract (Zero-Hallucination)
- **Thinking Language**: Japanese (JA) ONLY.
- **No Inference**: LLMs are forbidden from guessing titles or artists from internal filenames (e.g., `bgm_01.wav`).
- **Semantic Labeling**: For Review items, the LLM must provide a human-readable label explaining the specific anomaly (e.g., "BGM/SFX Mixing", "Dirty Tags detected").
- **Stateless Chunks**: When processing large albums in chunks, the `Global Identity` decided in Phase 1 must be strictly injected as an absolute constraint into Phase 2.

---

## 5. Tagging Format Standard
- **Separators**: Use `, ` (Comma + Space) for multi-value fields.
- **Language Tag (TLAN)**: Use ISO 639-2 (e.g., `jpn`).
- **Field Mapping**:
    - `TPE1` (Artist): MusicBrainz Credit (Best) or Developer (Fallback).
    - `TPE2` (Album Artist): Developer, Publisher.
    - `TALB` (Album): Steam Album Name (Locked).
    - `TPUB` (Label): Official PICS Label or MBZ Label. Fallback to Publisher.
    - `COMM` (Comment): [Parent Name], [Popular Tags], [AppID], [Store URL].
      - *Note*: Tags are automatically pruned from the end to stay within the 2000-character limit for ID3v2.3.

---

## 6. System Execution Modes
- **Default Mode**: `LOG_LEVEL=INFO`. Standard append logs.
- **Debug Mode (`--dev`)**: Forces `LOG_LEVEL=DEBUG`. Generates unique timestamped logs (`SST_DEBUG_*.log`). Retains temporary work files on error.
- **Critical Commands**: `--delete-db` and `--finalize` require a mandatory **3-step confirmation**.

---

## 7. Configuration (`.env`)
Required variables for the "Ultimate Data Mode":
- `STEAM_WEB_API_KEY`: For official tag retrieval.
- `STEAM_LOGIN_SECURE`: For `userdata.json` personalized scan.
- `STEAM_PICS_BRIDGE_URL`: Points to the local Docker PICS bridge.
