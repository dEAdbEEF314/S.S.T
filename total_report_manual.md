# S.S.T 処理結果 総合レポート生成手順書（AIエージェント向け）

## 📋 概要

本手順書は、`--fingerprint-all` オプション付きで処理された100件のバッチ実行結果を分析し、
以下の6セクションを含む**HTMLレポート**を `report/` ディレクトリ配下に生成するための
AIエージェント向けの完全な作業手順を定義する。

### 処理実績（バッチ結果HTMLから確認済み）

| ステータス | 件数 |
|-----------|------|
| Total | 100 |
| Archive | 51 |
| Review | 48 |
| Skip | 0 |
| Error | 1 |

### 生成するレポートのセクション構成

| # | セクション | 内容 |
|---|-----------|------|
| 1 | Archive送り | 件数・理由・処理フロー詳細 |
| 2 | 不自然なArchive送り | 件数・不自然と判断した根拠・処理フロー詳細 |
| 3 | Review送り | 件数・理由・処理フロー詳細 |
| 4 | 理不尽なReview送り | 件数・理不尽と判断した根拠・処理フロー詳細 |
| 5 | LLM決定とシステム処理の矛盾 | 矛盾の有無・原因 |
| 6 | エラー・失敗 | 件数・原因 |

### 出力先
- `report/total_analysis_report.html`（メインレポート）

---

## 🗂️ データソースマップ

レポート生成に必要なデータは以下の場所に存在する。

### 1. SQLiteデータベース（最重要・一次情報源）
- **パス**: `data/sst_local_state.db`
- **テーブル**: `processed_albums`
- **スキーマ**:
  ```sql
  CREATE TABLE processed_albums (
      app_id INTEGER PRIMARY KEY,
      status TEXT,           -- 'archive' | 'review' | 'error' | 'skip'
      album_name TEXT,
      processed_at TEXT,
      metadata_json TEXT     -- JSON文字列（後述の構造を持つ）
  );
  ```
- **`metadata_json` の主要フィールド**:
  ```json
  {
    "app_id": 12345,
    "album_name": "...",
    "status": "archive|review",
    "message": "[Dirty Tags x3, Duplicates (2)]",  // Validatorの判定結果
    "confidence_score": 100,                         // Identity Confidence (0-100)
    "integrity_quality": 95,                         // Integrity Quality (0-100)
    "archive_vs_review_ratio": {"archive": 80, "review": 20},
    "strategy": "STEAM_BASED|MBZ_BASED|FINGERPRINT_BASED|HYBRID|LOCAL_BASED|REVIEW_REQUIRED",
    "confidence_reason": "LLMによる推論理由テキスト",
    "processed_at": "2026-07-10T18:34:18+09:00",
    "tracks": [
      {
        "tags": {
          "title": "曲名",
          "artist": "アーティスト名",
          "track_number": "1",
          "disc_number": "1",
          "album_artist": "...",
          "genre": "...",
          "year": "2024"
        },
        "title_source": "MBZ|STEAM|LOCAL|EMBED",
        "source": "use_mbz|use_steam|use_local"
      }
    ],
    "steam_info": { "name": "...", "parent_name": "...", ... },
    "diagnostics": {
      "trace": [
        {"stage": "PROCESS_START", "details": {...}, "at": "..."},
        {"stage": "LLM_CONSOLIDATED", ...},
        {"stage": "VALIDATION_DONE", "details": {"status": "...", "message": "..."}, ...},
        {"stage": "PACKAGE_SAVE_START", ...},
        {"stage": "PACKAGE_SAVE_DONE", ...}
      ],
      "review_cause_code": "EARLY_REVIEW_RETURN|null",
      "upstream_cause_code": "LLM_RESPONSE_MISSING|LOW_CONFIDENCE_GATE|null",
      "packager_invoked": true
    }
  }
  ```

### 2. デバッグログ
- **パス**: `logs/SST_DEBUG_*.log`（最新のログファイルを使用）
- **用途**: エラー・例外の詳細追跡、処理フロー可視化
- **⚠️ 重要な制約**: このログファイルはエンコーディング問題（UTF-8 BOMまたは特殊エンコーディング）により、`rg`（ripgrep）や`grep`が全くヒットしない場合がある。その場合は `view_file` ツールまたは `python3` スクリプトでの読み込みを使用すること。
- **検索パターン例**:
  - `ERROR` — 致命的エラー
  - `WARNING` — 軽微な警告（Validator降格通知等）
  - `ファストトラック` — ファストトラック判定
  - `STEAM-TRUST` — Steam信頼パス発動
  - `致命的な失敗` — process_albumの例外キャッチ
  - `Audio encoding failed` — FFmpeg変換失敗
  - `response_truncated` — LLM応答切断

### 3. 中間生成物（DEBUGモード時のみ保持）
- **パス**: `sst-work/buffer_{AppID}_{RunID}/` — FFmpeg変換用の一時バッファ
- **パス**: `sst-work/final_{AppID}_{RunID}/` — タグ付け済みファイルとレポート
  - `json/metadata.json` — DB記録と同一の完全メタデータ
  - `json/llm_log.json` — LLMの生応答を含む完全ログ
  - `json/mbz_log.json` — MusicBrainz検索ログ
  - `AUDIT_REPORT.html` — 個別アルバムの監査レポート
  - `LLM_PROMPT.md` — LLMに送信された実際のプロンプト（存在する場合）

### 4. 最終生成物（ZIPアーカイブ）
- **Archive出力**: `output/archive/{AppID}_{SafeName}.zip`
- **Review出力**: `output/review/{AppID}_{SafeName}.zip`
- ZIPの内部構造は `sst-work/final_*` と同一（MP3ファイル + json/ + AUDIT_REPORT.html）

### 5. バッチ結果HTMLレポート（システム自動生成）
- **パス**: `output/Result_*.html`
- **用途**: 処理結果の一覧表（参考情報として使用可能）

---

## 🔧 前提条件

- `uv` がインストール済みであること
- `sqlite3` コマンドが使用可能であること
- `python3` が使用可能であること（`uv run` 経由で実行）
- `rg`（ripgrep）が使用可能であること

---

## 📐 実行手順

### Phase 1: データ収集

#### Step 1.1: データベースからの全件データ取得

以下のSQLクエリをPythonスクリプトで実行し、全処理結果を構造化データとして取得する。

```python
import sqlite3
import json
from pathlib import Path

db_path = Path("data/sst_local_state.db")
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT app_id, status, album_name, metadata_json FROM processed_albums")
rows = cur.fetchall()

results = []
for app_id, status, album_name, metadata_json in rows:
    meta = json.loads(metadata_json) if metadata_json else {}
    results.append({
        "app_id": app_id,
        "status": status,
        "album_name": album_name,
        "meta": meta
    })
conn.close()
```

#### Step 1.2: ログファイルからのエラー抽出

```bash
# エラーの抽出
rg --json "ERROR" logs/SST_DEBUG_*.log | head -100

# 致命的失敗の抽出
rg "致命的な失敗" logs/SST_DEBUG_*.log

# LLM応答切断の抽出
rg "response_truncated|done_reason.*length" logs/SST_DEBUG_*.log
```

#### Step 1.3: 中間生成物（sst-work）の確認

DEBUGモードで実行されている場合、`sst-work/final_*/json/llm_log.json` からLLMの生応答を確認できる。

```bash
# llm_log.json から Phase 1 のLLM生応答を確認
for f in sst-work/final_*/json/llm_log.json; do
    app_id=$(echo "$f" | grep -oP 'final_\K\d+')
    echo "=== AppID: $app_id ==="
    python3 -c "import json; d=json.load(open('$f')); p1=d.get('phase1_res',{}); print(f'  Conf: {p1.get(\"identity_confidence\")}, Qual: {p1.get(\"integrity_quality\")}, Strategy: {p1.get(\"strategy\")}')"
done
```

---

### Phase 2: 分析と分類

#### セクション1: 「Archive送り」の分析

**定義**: `status == 'archive'` のレコード全件。

**必要な情報の抽出**:

```sql
SELECT app_id, album_name,
       json_extract(metadata_json, '$.message') as message,
       json_extract(metadata_json, '$.confidence_score') as conf,
       json_extract(metadata_json, '$.integrity_quality') as qual,
       json_extract(metadata_json, '$.strategy') as strategy,
       json_extract(metadata_json, '$.confidence_reason') as reason
FROM processed_albums
WHERE status = 'archive';
```

**分類基準（理由パターン）**:

| パターン | 意味 | 処理フロー |
|----------|------|-----------|
| `Success [MBZ Match+AcoustID]` | 音声指紋＋MBZスコアリングにより同定成功 | Scan→Fingerprint→MBZ→LLM Phase1→Phase2→Tagger→Validator(Pass)→Packager(archive) |
| `Success [Steam Trust+AcoustID]` | 音声指紋あり＋Steam信頼パス | Scan→Fingerprint→Steam構造一致→LLM(STEAM-TRUST)→Phase2→Tagger→Validator(Pass, Quality≥75)→Packager(archive) |
| `Success [Steam Trust]` | Steam信頼パスのみ（指紋なし） | Scan→Steam PICS→構造一致→LLM(STEAM-TRUST)→Phase2→Tagger→Validator(Pass, Quality≥75)→Packager(archive) |
| `Success [MBZ Match]` | MBZ検索スコアのみで同定 | Scan→MBZ Search→スコアリング→LLM Phase1→Phase2→Tagger→Validator(Pass)→Packager(archive) |
| `Success [Steam Fallback]` | MBZなし、Steam情報で処理 | Scan→Steam Only→LLM→Phase2→Tagger→Validator(Pass)→Packager(archive) |

**処理フローの共通ステージ**:
1. `PROCESS_START`: ライブラリスキャン、オーディオファイル検出
2. `FILES_SCANNED`: 音声ファイル数の確認
3. `TRACK_GROUPS_BUILT`: 論理トラックへのグルーピング
4. `VIRTUAL_ALBUM_FINGERPRINT_BUILT`: AcoustID指紋による仮想アルバム構築
5. `VIRTUAL_ALBUM_MBZ_SEARCH_BUILT`: MBZ検索による仮想アルバム構築
6. `LLM_CONSOLIDATED`: LLMによるPhase1（Global Identity）+ Phase2（Sequential Mapping）の完了
7. `VALIDATION_DONE`: Validator検閲の通過（issues=[])
8. `PACKAGE_SAVE_START` → `PACKAGE_SAVE_DONE`: ZIPアーカイブの出力

---

#### セクション2: 「不自然なArchive送り」の検出

**定義**: Archive判定が下されているが、以下のいずれかの条件に該当し、人間の目から見ると疑わしいケース。

**検出基準（異常検知ルール）**:

| ルール | 検出条件 | 根拠 |
|--------|----------|------|
| **タイトル乖離** | `album_name`（Steam上の正式名称）と、MBZから採用された`tracks[].tags.album`の文字列類似度が40%未満 | 全く別のリリースのメタデータが適用された可能性がある |
| **策略ミスマッチ** | `strategy=FINGERPRINT_BASED` だが `confidence_score < 100` | 指紋ベースなのに確信度が不完全 |
| **LLM矛盾救済** | `archive_vs_review_ratio.review > 50` にもかかわらず `status=archive` | LLMはReviewを推奨していたが、スコアが閾値を超えていたためシステムが強行した (`validator.py` L96-100 の `is_score_perfect` ロジック) |
| **疑わしいTrack Count差** | Archiveされたがトラック数がSteam公式リストと2割以上乖離 | 不完全な同定の可能性 |

**分析方法**:

```python
# 不自然なArchive検出
for r in archive_results:
    meta = r["meta"]
    # 1. タイトル乖離チェック
    for track in meta.get("tracks", []):
        mbz_album = track.get("tags", {}).get("album", "")
        if mbz_album and string_similarity(meta["album_name"], mbz_album) < 0.4:
            flag_unnatural(r, "タイトル乖離", f"Steam: {meta['album_name']} vs MBZ: {mbz_album}")

    # 2. LLM矛盾救済チェック
    ratio = meta.get("archive_vs_review_ratio", {})
    if ratio.get("review", 0) > 50:
        flag_unnatural(r, "LLM矛盾救済", f"LLM Review率: {ratio['review']}% だがスコア {meta['confidence_score']}/{meta['integrity_quality']} で Archive強行")

    # 3. Track Count差チェック
    steam_track_count = len(meta.get("steam_info", {}).get("store_tracklist", []))
    actual_track_count = len(meta.get("tracks", []))
    if steam_track_count > 0 and abs(steam_track_count - actual_track_count) / steam_track_count > 0.2:
        flag_unnatural(r, "Track Count乖離", f"Steam: {steam_track_count}, 実際: {actual_track_count}")
```

---

#### セクション3: 「Review送り」の分析

**定義**: `status == 'review'` のレコード全件。

**必要な情報の抽出**:

```sql
SELECT app_id, album_name,
       json_extract(metadata_json, '$.message') as message,
       json_extract(metadata_json, '$.confidence_score') as conf,
       json_extract(metadata_json, '$.integrity_quality') as qual,
       json_extract(metadata_json, '$.confidence_reason') as reason,
       json_extract(metadata_json, '$.diagnostics.review_cause_code') as cause,
       json_extract(metadata_json, '$.diagnostics.upstream_cause_code') as upstream
FROM processed_albums
WHERE status = 'review';
```

**Review理由のカテゴリ分類**:

`message` フィールドは `[理由1, 理由2, ...]` 形式のブラケット付きCSV。以下のパターンで分類する。

| 理由パターン（messageの部分一致） | カテゴリ | 意味 | 処理フロー |
|----------------------------------|----------|------|-----------|
| `Track#0 x{N}` | 物理的欠損 | トラック番号が0のまま補完不能 | Tagger→Validator(Track#0検知)→Packager(review) |
| `Unknown Title x{N}` | 物理的欠損 | タイトルが"Unknown"のまま | Tagger→Validator(Unknown Title検知)→Packager(review) |
| `Dirty Tags x{N}` | タグ汚染 | 曲名にトラック番号が混入（"01. Title"等）しておりMBZ/Steam公式名称と不一致 | LLM→Tagger→Validator(dirty_pattern検知)→Packager(review) |
| `Duplicates ({N})` | 重複トラック | 同一ディスク内に同じトラック番号が複数存在 | LLM→Smart Duplicate Resolution失敗→Validator(重複検知)→Packager(review) |
| `Duplicate Titles ({N}/{total})` | 重複タイトル | 全トラックの50%以上が同一曲名（LLMハルシネーション防止装置） | LLM→Tagger→Validator(Counter検知)→Packager(review) |
| `Quality too low ({N}%)` | 品質不足 | LLMの`integrity_quality`が閾値（通常95、STEAM-TRUST時75）未満 | LLM Phase1(低品質判定)→Validator(閾値未達)→Packager(review) |
| `Confidence too low ({N}%)` | 確信度不足 | `identity_confidence`が100未満 | LLM Phase1(低確信度)→Validator(閾値未達)→Packager(review) |
| `LLM's decision` | LLM判断 | LLMが`archive_vs_review_ratio`でReview寄りの判定 | LLM Phase1(Review推奨)→Validator(比率チェック)→Packager(review) |
| `CRITICAL: Audio Source Error` | 音声エラー | FFmpegでの変換/デコードに失敗 | Tagger(FFmpeg失敗)→Validator(audio_fail=True)→Packager(review) |
| `Audio quality warning` | 音声警告 | FFmpegで警告が出力された（invalid rice order等） | Tagger(FFmpeg警告)→Validator(audio_warn=True)→Packager(review) |
| `LLM Failure: ...` | LLM失敗 | LLMの推論そのものが失敗（タイムアウト、JSON不正等） | LLM→consolidate失敗→EARLY_REVIEW_RETURN→DB記録(review) |
| `Low Confidence: ...` | 低確信度 | Phase1で確信度が基準に達せず、Phase2に進まなかった | LLM Phase1→EARLY_REVIEW_RETURN→DB記録(review) |

**diagnostics（診断トレース）の活用**:

- `review_cause_code == "EARLY_REVIEW_RETURN"`: Phase2以前に処理中断。Validatorの判定ではなくLLMの問題。
  - `upstream_cause_code == "LLM_RESPONSE_MISSING"`: LLMが応答を返さなかった
  - `upstream_cause_code == "LOW_CONFIDENCE_GATE"`: LLMの確信度が基準未達
  - **⚠️ `EARLY_REVIEW_RETURN` のレコードは `metadata_json` に `message` フィールドが存在しない。** 同様に `integrity_quality`, `archive_vs_review_ratio`, `strategy` も欠落する。`db.py` はこの状態を検知して `logger.warning` を出力するが、エラーとして扱わない。分析スクリプトでは `message` が `None` / 未設定の場合のフォールバック処理が必要。
- `review_cause_code == null`: Validatorの物理チェックによる降格（正常なフロー）
- `packager_invoked == true`: タグ付け・変換まで正常到達後のValidator降格
- `packager_invoked == false`: Phase1/Phase2段階での処理中断

---

#### セクション4: 「理不尽なReview送り」の検出

**定義**: Reviewに送られているが、LLMの判定（confidence/quality）自体は十分高く、
システム側の物理チェック（Validator）によって強制降格されたケース。

**検出基準**:

| ルール | 検出条件 | 根拠 |
|--------|----------|------|
| **高確信度オーバーライド** | `confidence_score >= 100` かつ `status == 'review'` | LLMは100%確信していたが、Validatorの物理チェック（Dirty Tags/Duplicates/Track#0等）に引っかかった |
| **高品質オーバーライド** | `confidence_score >= 100` かつ `integrity_quality >= 95` かつ `status == 'review'` | LLMスコアは完全だが、それでもValidatorが物理エラーを検出した。特に厳格なDirty Tags検知が原因の場合、MBZ公式タイトルが番号付き形式であれば偽陽性の可能性がある |
| **Steam-Trust品質閾値近辺** | `confidence_score >= 100` かつ `integrity_quality` が 70〜74% の範囲 かつ `strategy` が STEAM系 | STEAM-TRUST閾値（75%）にわずかに届かなかったケース |

**分析方法**:

```sql
-- 高確信度なのにReview（理不尽候補）
SELECT app_id, album_name,
       json_extract(metadata_json, '$.message') as validator_msg,
       json_extract(metadata_json, '$.confidence_score') as conf,
       json_extract(metadata_json, '$.integrity_quality') as qual,
       json_extract(metadata_json, '$.confidence_reason') as reasoning
FROM processed_albums
WHERE status = 'review'
  AND json_extract(metadata_json, '$.confidence_score') >= 100;
```

**理不尽判定のフロー詳細**:
1. LLM Phase1 → `identity_confidence=100`, `integrity_quality≥95` を返却
2. LLM Phase2 → トラックマッピング完了
3. Tagger → MP3タグ書き込み完了
4. **Validator介入**: 物理チェックで `issues` を検出
   - 例: `Dirty Tags x1`（曲名に "01. " が残存 → MBZ公式タイトルが番号付きの場合は偽陽性）
   - 例: `Duplicates (1)`（Smart Rescue Logicが解決しきれなかった僅差の重複）
5. `issues` が存在するため `status = "review"` に強制降格
6. Packager → `output/review/` へZIP出力

---

#### セクション5: LLMの決定とシステム処理の矛盾の検出

**定義**: LLMが下した判定（Phase1の確信度・品質・推奨比率）と、
最終的なシステムの処理結果（status）が矛盾しているケース。

**矛盾パターン**:

| パターン | LLMの判定 | システムの処理 | 原因 |
|----------|----------|---------------|------|
| **LLM Archive推奨 → System Review** | `confidence=100`, `quality≥95`, `archive_ratio>50` | `status=review` | Validatorの物理チェック（Dirty Tags/Duplicates等）が優先された |
| **LLM Review推奨 → System Archive** | `archive_ratio<50` または `strategy=REVIEW_REQUIRED` | `status=archive` | `is_score_perfect`（`conf≥100 && qual≥threshold`）が`True`のため、LLMの比率判定をオーバーライド（`validator.py` L96-100）|
| **LLM低確信度 → System Archive** | `confidence<100` | `status=archive` | STEAM-TRUSTヒューリスティックがLLMの確信度を100に引き上げた場合（`llm.py`内） |
| **LLM Phase1 成功 → EARLY_REVIEW_RETURN** | Phase1応答は正常 | `review_cause_code=EARLY_REVIEW_RETURN` | Phase2が失敗（タイムアウト/JSON不正）したため、Phase1のスコアに関わらず中断 |

**分析方法**:

```python
for r in all_results:
    meta = r["meta"]
    ratio = meta.get("archive_vs_review_ratio", {})
    conf = meta.get("confidence_score", 0)
    qual = meta.get("integrity_quality", 0)
    status = meta.get("status")

    # パターン1: LLM Archive推奨 → System Review
    if conf >= 100 and qual >= 95 and ratio.get("archive", 0) > 50 and status == "review":
        flag_contradiction("LLM Archive推奨 → System Review", r)

    # パターン2: LLM Review推奨 → System Archive
    if (ratio.get("review", 0) > 50 or ratio.get("archive", 0) < 50) and status == "archive":
        flag_contradiction("LLM Review推奨 → System Archive", r)

    # パターン3: Phase1成功 → 早期Review
    diag = meta.get("diagnostics", {})
    if diag.get("review_cause_code") == "EARLY_REVIEW_RETURN" and conf > 0:
        flag_contradiction("Phase1成功 → EARLY_REVIEW_RETURN", r)
```

---

#### セクション6: エラー・失敗の分析

**定義**: 処理パイプラインの途中で例外が発生し、正常な Archive/Review フローを完遂できなかったケース。

**検出方法**:

1. **DBからのerrorステータス**:
   ```sql
   SELECT app_id, album_name, metadata_json
   FROM processed_albums
   WHERE status = 'error';
   ```

2. **ログファイルからのエラー抽出**:
   ```bash
   # 致命的例外（process_albumのexceptブロック）
   rg "致命的な失敗" logs/SST_DEBUG_*.log

   # FFmpeg変換エラー
   rg "Audio encoding failed|FFmpeg.*error|FFmpeg.*Error" logs/SST_DEBUG_*.log

   # LLM通信エラー
   rg "LLM.*timeout|LLM.*error|response_truncated" logs/SST_DEBUG_*.log

   # API通信エラー
   rg "AcoustID.*error|MusicBrainz.*error|PICS.*error" logs/SST_DEBUG_*.log

   # ディスクI/Oエラー
   rg "Permission denied|No space left|IOError|OSError" logs/SST_DEBUG_*.log
   ```

3. **diagnosticsからのエラー追跡**:
   ```python
   for r in all_results:
       diag = r["meta"].get("diagnostics", {})
       for trace_entry in diag.get("trace", []):
           if trace_entry.get("stage") == "EXCEPTION_FALLBACK":
               # 例外フォールバックが記録されている
               error_detail = trace_entry.get("details", {})
               record_error(r, error_detail.get("error"), error_detail.get("error_type"))
   ```

**エラーカテゴリ**:

| カテゴリ | 原因例 | 影響 |
|----------|--------|------|
| LLM推論失敗 | タイムアウト(600s超過)、不正JSON返却、応答切断(done_reason=length) | Review降格 (EARLY_REVIEW_RETURN) |
| FFmpeg変換失敗 | 破損した音声ファイル、未対応フォーマット、デコードエラー | Review降格 (Audio Source Error) |
| 外部API失敗 | AcoustID/MBZ/PICSのタイムアウト・HTTP503 | 指紋/MBZ候補なしで続行（Graceful Degradation） |
| ファイルI/O失敗 | 権限エラー、ディスク容量不足 | Error ステータスで記録 |
| 致命的例外 | 予期せぬPython例外 | Error ステータスで記録、次のAppIDへ続行 |

---

### Phase 3: HTMLレポート生成

#### Step 3.1: 分析スクリプトの作成

以下のPythonスクリプトを `report/generate_total_report.py` として作成し実行する。

**スクリプトの要件**:

1. **データ収集**: SQLiteから全レコードを取得し、ログファイルからエラー情報を補完
2. **分類**: 上記Phase 2の全ルールに基づいて分類
3. **HTML生成**: 以下の構造を持つHTMLファイルを出力

**HTMLレポートの構造要件**:

```
report/total_analysis_report.html
├── ヘッダー（タイトル、生成日時、処理概要サマリー）
├── セクション1: Archive送り
│   ├── 件数サマリー（理由パターン別の集計表）
│   ├── 理由パターン別の処理フロー解説
│   └── 全Archive対象の一覧テーブル（AppID, Album, Score, Strategy, Message）
├── セクション2: 不自然なArchive送り
│   ├── 検出件数
│   ├── 各件の不自然と判断した根拠（タイトル乖離、LLM矛盾救済等）
│   └── 処理フロー詳細（どのステージでどの判定が行われたか）
├── セクション3: Review送り
│   ├── 件数サマリー（理由カテゴリ別の集計表）
│   ├── 理由カテゴリ別の処理フロー解説
│   └── 全Review対象の一覧テーブル（AppID, Album, Conf, Qual, Message, Reason, Cause Code）
├── セクション4: 理不尽なReview送り
│   ├── 検出件数
│   ├── 各件の理不尽と判断した根拠
│   └── 処理フロー詳細（LLMの判定 vs Validatorの判定の比較）
├── セクション5: LLM決定 vs システム処理の矛盾
│   ├── 矛盾の有無（あり/なし）
│   ├── 矛盾パターン別の件数
│   └── 各矛盾ケースの原因詳細（LLM出力値 vs Validator出力値）
├── セクション6: エラー・失敗
│   ├── 件数（カテゴリ別集計）
│   ├── 各エラーの原因と対象AppID
│   └── ログからの関連エラーメッセージ抜粋
└── フッター（生成情報）
```

**HTMLデザイン要件**:
- S.S.T既存のダークテーマ（`report_generator.py` の CSS に準拠: `--bg-color: #0d1117`, `--card-bg: #161b22` 等）
- テーブルはソート不要だがホバーエフェクトを付与
- 各セクションはアンカーリンクで目次からジャンプ可能
- AppIDにはSteam Storeへのリンクを付与（`https://store.steampowered.com/app/{AppID}`）
- 処理フロー図はテキストベースのフローチャート（Mermaid不要、CSS矢印で表現）

#### Step 3.2: 実行

```bash
cd /workspace/S.S.T
uv run python report/generate_total_report.py
```

#### Step 3.3: 検証

生成された `report/total_analysis_report.html` を確認し、以下をチェック：
- [ ] 全6セクションが存在すること
- [ ] Archive + Review + Error + Skip の合計がDB上の全レコード数と一致すること
- [ ] 「不自然なArchive」と「理不尽なReview」の件数に虚偽がないこと（SQLで再検証）
- [ ] HTMLが正しくレンダリングされること

---

## 🔑 既存ツール・スクリプトの活用

### 既存バッチ分析スクリプト（簡易版）
- **パス**: `.agents/skills/sst-batch-inspector/scripts/analyze_batch_results.py`
- **機能**: ステータス分布、Archive/Reviewパターン、不自然Archive/Review候補を出力
- **注意**: DB パスがハードコードされている（`/home/sexyroot/src/S.S.T/data/sst_local_state.db`）ため、実行前にパス修正が必要
- **実行**: `uv run python .agents/skills/sst-batch-inspector/scripts/analyze_batch_results.py`

### 高度な分析スクリプト（推奨）
- **パス**: `Maintenance/analyze_processing_results.py`（276行）
- **機能**: 上記簡易版の全機能に加え、以下を実行
  - `review_cause_code` / `upstream_cause_code` の分布分析
  - `message` 欠落行の原因別内訳
  - DB上の `review` 件数と `output/review/` ファイルシステムの実体差分
  - 不自然Archive/Review検出
  - 分析結果をJSONファイルとして保存
- **実行**: `uv run python Maintenance/analyze_processing_results.py`
- **注意**: `docs/LOGIC.md` および `docs/error_handling.md` では `tests/analyze_processing_results.py` として参照されているが、実際のパスは `Maintenance/` 配下

### 個別アプリ調査スクリプト
- **パス**: `tests/investigate_app.py`（存在する場合）
- **機能**: 特定AppIDのDB記録とZIP内ログを表示
- **実行**: `uv run python tests/investigate_app.py <AppID>`

---

## 📊 判定ロジックの参照先（ソースコード）

レポートで言及する処理フローを正確に記述するため、以下のソースコードを参照すること。

| モジュール | パス | 主要な責務 |
|-----------|------|-----------|
| `processor.py` | `src/sst/processor.py` | `process_album()`: メイン処理パイプライン、diagnostics記録、EARLY_REVIEW_RETURN判定 |
| `validator.py` | `src/sst/validator.py` | `validate()`: 物理検閲ゲート（Track#0, Dirty Tags, Duplicates, 信頼度閾値チェック） |
| `llm.py` | `src/sst/llm.py` | `consolidate_virtual_albums()`: LLM推論（Phase1/1.5/2）、STEAM-TRUST判定 |
| `packager.py` | `src/sst/packager.py` | `save_local_package()`: ZIP生成、output/{archive|review}/配下への出力 |
| `report_generator.py` | `src/sst/report_generator.py` | HTML/Markdownレポート生成テンプレート |
| `virtual_album.py` | `src/sst/virtual_album.py` | 仮想アルバム構築（STEAM, FINGERPRINT, MBZ_SEARCH, LOCAL） |
| `track_grouper.py` | `src/sst/track_grouper.py` | 論理トラック統合、AcoustID照合 |
| `db.py` | `src/sst/db.py` | `record_processed()`: DB記録 |

## 📝 ドキュメント参照先

| ドキュメント | パス | 内容 |
|-------------|------|------|
| LOGIC.md | `docs/LOGIC.md` | 判定ロジック完全仕様（三権分立、スコアリング、LLMフェーズ、Validator） |
| SST.md | `docs/SST.md` | コアアーキテクチャ概要 |
| data_flow_diagram.md | `docs/data_flow_diagram.md` | Mermaidフローチャート |
| error_handling.md | `docs/error_handling.md` | エラーハンドリング仕様 |
| VIRTUAL_ALBUM_RULES.md | `docs/VIRTUAL_ALBUM_RULES.md` | 仮想アルバム統合ルール |
| AGENT_GUIDE.md | `docs/AGENT_GUIDE.md` | 信頼度ゲート判定基準 |

---

## ⚠️ 注意事項

1. **Steam ライブラリへの書き込み厳禁**: 分析は読み取りのみ。出力は `report/` ディレクトリへ。
2. **DBの直接変更厳禁**: `data/sst_local_state.db` はSELECTのみ。
3. **既存出力の変更厳禁**: `output/archive/`, `output/review/` 内のZIPファイルは読み取り専用。
4. **sst-workの一時ファイル**: DEBUGモード時のみ保持されている。参照のみ。
5. **文字列類似度の計算**: Levenshtein距離ベースの正規化類似度を使用すること（既存の `analyze_batch_results.py` の実装を参考に）。
6. **日本語での説明**: GEMINI.mdの規定に従い、作業の説明は日本語で行うこと。
