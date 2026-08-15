# LLM Mapping JSON 統一計画: `slots` 単一フォーマットへの移行 & 前処理正規化

> **ステータス**: 計画確定・実装待ち  
> **更新日**: 2026-08-16  
> **関連仕様**: [METADATA_SOURCE_SPEC.md §3.8, §5, §6, §11.4](docs/METADATA_SOURCE_SPEC.md)

---

## 1. 背景と目的

100件規模の実データバッチ検証（Archive 87件 / Review 13件）およびコード分析により、以下の課題が明確になった。

### 課題一覧

| # | 課題 | 影響 | 対処方針 |
|---|------|------|----------|
| 1 | `slots` と `track_instructions` の二重構造 | LLM出力の約40-50%が冗長、不整合リスク | `slots` 単一フォーマットへ統一（仕様§6.3準拠） |
| 2 | `action` フィールドの実効性不足 | 4値中2値しか実質消費されず | LLM前段の **プレマッチ層** に移行し、`action` を内部形式から完全廃止 |
| 3 | HTML実体参照（`&amp;` 等）によるFast-Track漏れ | `Tropico 6` (76曲) 等の巨大アルバムで不要なLLM呼出が発生 | PICS取得時および `normalize_title` に `html.unescape` を適用 |
| 4 | 未割当ファイル（Unassigned Files）の品質保証 | 余剰ファイル存在時のライブラリ信頼性 | **厳格に Review 送りを維持** し、`AUDIT_REPORT.html` に目立つよう明示 |

---

## 2. 設計決定

| # | 決定事項 | 選択 | 理由 |
|---|---------|------|------|
| 1 | LLM出力フォーマット | **`slots` のみ** | トークン40-50%削減、仕様§6.3との整合性、不整合リスク排除 |
| 2 | `action` フィールド | **内部形式から完全廃止** | `matched_v_idx` の有無で等価に代替可能 |
| 3 | `override_track` / `override_disc` | **プロンプト廃止、内部保持** | Fast-Trackおよび正規化層が内部的に使用するため |
| 4 | HTML実体参照のデコード | **PICS取得時・正規化時に適用** | `&amp;` 不一致によるFast-Trackすり抜けの根絶 |
| 5 | ファイル名中間数字の正規表現抽出 | **不採用（導入しない）** | 自由文字列への過剰正規表現マッチによる誤推測・削りすぎリスクを排除 |
| 6 | Steam充足時の Unassigned Files | **Review送りを厳格維持** | 「Archive判定＝ノーチェックでライブラリ追加可能」の信頼度を死守。`AUDIT_REPORT.html` で目立つよう強調表示 |

---

## 3. 変更計画

### 3.1 前処理正規化の強化（HTML実体参照デコード）

#### [MODIFY] `src/sst/steam_web_api.py`
- PICSトラックリスト取得時（`originalname` 格納時）およびテキストトラックリスト抽出時に `html.unescape()` を適用。

#### [MODIFY] `src/sst/track_grouper.py`
- `TrackManager.normalize_title()` の先頭で `html.unescape()` を適用し、ファイル名・メタデータ側の実体参照も吸収。

---

### 3.2 プレマッチ層の新設

#### [NEW] `src/sst/llm/prematch.py`

LLM呼び出し前に、ローカルファイルと ACOUSTID / MBZ シグナルの対応関係を機械的に解決する新モジュール。

**責務**:
- ローカルファイルの `file_id` と ACOUSTID Recording の紐付け（再生時間 + MBID 一致で特定）
- 紐付いた Recording の `release_position` → Steam スロットへの事前マッピング候補生成
- MBZ_SEARCH トラックとの title similarity マッチング
- 結果を `file_prematch_map: Dict[str, PrematchResult]` として返却

```python
@dataclass
class PrematchResult:
    """LLM呼び出し前に解決済みのシグナル-スロット対応"""
    file_id: str
    acoustid_steam_slot: Optional[int]    # AcoustID → Steam slot 候補
    mbz_track_index: Optional[int]        # MBZ Release 内のトラックインデックス
    mbz_search_steam_slot: Optional[int]  # MBZ_SEARCH → Steam slot 候補
    evidence: List[str]                   # マッチの根拠 (e.g. ["acoustid", "duration"])
```

**移行対象ロジック** (`_merge_track_instructions` L198-215):
- `use_fingerprint` → `ref_fingerprint[mv_idx]` から `mbz_track_index` と `override_track` を解決
- `use_mbz_search` → `full_ref_mbz_search[mv_idx]` から同様に解決
- `use_steam` → `full_ref_steam[mv_idx]` から `override_track` を解決

---

### 3.3 プロンプト簡素化

#### [MODIFY] `src/sst/llm/prompts.py`

`build_mapping_prompt` の出力フォーマットを以下に変更:

```json
{
  "slots": {
    "STEAM_SLOT_NUMBER": {
      "files": ["FILE_ID"],
      "confidence": 0.95,
      "reason": "Brief reason (max 20 chars)"
    }
  },
  "unassigned_files": ["FILE_ID"],
  "unassigned_reason": "Brief reason if any"
}
```

**変更点**:
- `track_instructions` ブロック全体を削除
- `action`, `matched_v_idx`, `override_track`, `override_disc` の LLM への要求を廃止
- ルール 5-6 (`matched_v_idx` / `override` 関連) を削除
- `reason` の制限を `max 20 chars` に短縮
- プレマッチ結果を入力セクションに参考情報として追加

---

### 3.4 正規化層の簡素化

#### [MODIFY] `src/sst/llm/organizer.py`

##### `_normalize_track_mapping_result` (L259-295)
- `slots` → `track_instructions` 変換ロジックを廃止
- `slots` のキー（Steam スロット番号）から `matched_v_idx` を解決し、プレマッチ結果と結合して最終 instruction dict を直接生成
- 移行期間中は旧 `track_instructions` 形式の防御コードを残し、互換性を維持

##### `_merge_track_instructions` (L152-237)
- L198-215 の `action` 分岐（`use_fingerprint` / `use_mbz_search` / `use_steam`）を削除
- `override_title: None` のハードコード (L284) を削除
- `matched_v_idx` はプレマッチ結果 or スロットキーから解決済みのため、単純な dict.update に簡素化

##### `_process_track_mapping_segment` (L455-547)
- `prematch_map` を引数に追加

##### `align_slots` (L619-774)
- プレマッチ層の呼び出しを Phase1 (Identity) と Phase2 (Mapping) の間に挿入

---

### 3.5 消費コードの更新

#### [MODIFY] `src/sst/builder.py`
- L97: `instr.get("action") != "use_local"` → `instr.get("matched_v_idx") is not None` に変更
- L163: `instr.get("action") == "use_steam"` → `instr.get("matched_v_idx") is not None` に変更

#### [MODIFY] `src/sst/processor_support.py`
- L268: `instr.get("action") in ["use_steam", "use_fingerprint"]` → `instr.get("matched_v_idx") is not None` に変更

#### [MODIFY] `src/sst/processor.py`
- L232-233: Fast-Track 生成コードから `action` を削除

---

### 3.6 監査レポート表示の強化

#### [MODIFY] `src/sst/report_generator.py`
- Steam スロットが 100% 充足しているにもかかわらず `unassigned_files` が存在する場合、`AUDIT_REPORT.html` に「⚠️ **Steamスロット充足（余剰未割当ファイルあり）**」と明確に警告バッジを表示し、未割当となったファイル一覧を明示。

---

### 3.7 仕様書の更新

#### [MODIFY] `docs/METADATA_SOURCE_SPEC.md`
- §3.8: 文字列のエスケープ解除（HTML実体参照のデコード）を新設
- §5: HTML実体参照のアンエスケープ規則を明記
- §6.2.1: プレマッチ層（LLM呼び出し前のシグナル解決）を新設
- §6.3: 出力フォーマットを `slots` 単一に更新
- §11.4: 未割当ファイル（Unassigned Files）の品質保証規則を新設

#### [MODIFY] `CHANGE_HISTORY.md`
- 先頭に変更履歴を追記。

---

## 4. 変更影響マトリクス

| ファイル | 変更種別 | 影響度 | 概要 |
|---------|---------|-------|------|
| `src/sst/llm/prematch.py` | **新規** | — | プレマッチ層 |
| `src/sst/steam_web_api.py` | 修正 | 小 | HTML実体参照アンエスケープ |
| `src/sst/track_grouper.py` | 修正 | 小 | `normalize_title` に unescape 適用 |
| `src/sst/llm/prompts.py` | 修正 | 中 | `track_instructions` 削除、ルール簡素化 |
| `src/sst/llm/organizer.py` | 修正 | **大** | 正規化層の簡素化、プレマッチ統合 |
| `src/sst/builder.py` | 修正 | 小 | `action` → `matched_v_idx` 有無に変更 |
| `src/sst/processor_support.py` | 修正 | 小 | `action` → `matched_v_idx` 有無に変更 |
| `src/sst/processor.py` | 修正 | 小 | Fast-Track の `action` 削除 |
| `src/sst/report_generator.py` | 修正 | 小 | 未割当ファイルの警告強調表示 |
| `docs/METADATA_SOURCE_SPEC.md` | 修正 | 中 | §3.8, §5, §6.2.1, §6.3, §11.4 更新 |
| `CHANGE_HISTORY.md` | 追記 | — | 変更履歴 |

---

## 5. テスト計画

### 5.1 新規テスト

#### [NEW] `tests/test_prematch.py` — プレマッチ層の単体テスト
- `test_acoustid_match_resolves_steam_slot`: ACOUSTID Recording と Steam スロットが再生時間差 ±3s で正しく紐付くこと
- `test_acoustid_no_match_returns_none`: 再生時間差 3s 超でマッチしないこと
- `test_mbz_search_match_by_track_number`: MBZ_SEARCH トラック番号と Steam スロットの一致検証
- `test_prematch_with_no_signals`: シグナル不在時のフォールバック
- `test_prematch_multiformat_same_slot`: 異フォーマットが同一スロットに事前マッチすること
- `test_prematch_evidence_tracking`: 根拠追跡の検証

#### [NEW] `tests/test_html_unescape.py` — HTML実体参照のテスト
- `test_steam_pics_tracklist_unescaped`: Steam PICS の `&amp;` が `&` にデコードされること
- `test_track_manager_normalize_title_unescape`: `normalize_title` で `&amp;` や `&#39;` が正しく処理され一致判定されること

### 5.2 既存テストの更新
- `tests/test_llm_schema_normalization.py`: `action` 削除、プレマッチ結合テスト追加
- `tests/test_id3_tag_construction.py`: `matched_v_idx` ベースの分岐テストへ更新
- `tests/test_fast_track.py`: `action` 削除の追従

### 5.3 統合検証
- 既存ユニットテスト全通過（`uv run python -m pytest tests/ -v`）
- バッチテスト（`./sst --limit 10 --dev`）での回帰確認

---

## 6. 実装順序

```
1. steam_web_api.py & track_grouper.py の HTML unescape 適用 + test_html_unescape.py
2. prematch.py 新設 + test_prematch.py 新設
3. prompts.py 簡素化
4. organizer.py 正規化層の改修
5. builder.py / processor_support.py / processor.py の action 廃止
6. report_generator.py の Unassigned 警告強調
7. 既存テスト更新
8. uv run python -m pytest tests/ -v で全テスト通過確認
9. ./sst --limit 10 --dev で統合確認
10. docs/METADATA_SOURCE_SPEC.md 更新
11. CHANGE_HISTORY.md 追記
```
