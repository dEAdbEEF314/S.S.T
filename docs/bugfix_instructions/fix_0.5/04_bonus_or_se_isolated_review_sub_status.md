# 修正作業指示書 fix_0.5-04: 余剰ボーナス・効果音混入アルバムへのサブステータス付与規約

## 1. 課題と目的

### 現状の課題
- Steam サウンドトラックの中には、Steam 公式トラックリストに記載された全楽曲スロットが 100% 完璧に充足され、重複・欠落・音声破損・Track 0 等の異常が一切ないにもかかわらず、開発元が配布フォルダ内に Steam トラックリスト未記載の「ボーナストラック（未収録音源）」や「ゲーム内効果音（車両エンジン音、クラッシュ音、UI効果音等）」を同梱しているケースがある（例: FlatOut 4 `1299740`, 30XX `1553350`, Dead Estate `1806720`, NecroDancer `584382` 等）。
- S.S.T システムの原則（Steam を構造の絶対的正とし、未割当ファイルがある場合は安全のため Review に送る）に基づき、これらは正当に Review 送りとなっている。
- しかし、人手監査（レビューフォルダやレポート確認）において、「本編は完全に揃っており即座にアーカイブ投入可能（余剰ファイルが隔離されただけ）」なのか、「本編に欠落・破損・スワップ等の不備がある重大な Review」なのかを一目で識別できず、目視確認・ログ精査の運用コストが高かった。

### 目的
- 本編スロットが 100% 充足され、致命的異常がなく、Review 要因が余剰ファイルの未割当隔離のみであるアルバムに対し、明確なサブステータス `BONUS_OR_SE_ISOLATED` を自動付与する。
- ログ、DBメタデータ、HTMLレポート、および Discord 通知において本サブステータスを明示し、監査者が迷わず「本編健全」と即断できるようにする。

---

## 2. 判定規約と仕様

### サブステータス付与条件
アルバムの最終ステータスが `review` の場合、以下の全条件を満たす場合にサブステータス `BONUS_OR_SE_ISOLATED` を付与する：

1. **本編スロットの完全充足**:
   - `steam_expected_slots > 0`
   - `final_adopted_slots == steam_expected_slots`
   - `final_duplicate_slots == 0`
2. **余剰ファイルの存在**:
   - `unassigned_file_count > 0`
3. **本編の健全性保証（致命的異常がゼロであること）**:
   - `audio_fail is False` かつ `audio_warn is False`（音声破損・品質警告なし）
   - `track_zero_count == 0`（Track #0 なし）
   - `anomalous_unknown_count == 0`（異常な Unknown タイトルなし）
   - `official_title_mismatch_count == 0`（公式タイトル乖離なし）
   - `duplicate_output_path_count == 0`（出力パス重複なし）
   - `artifact_issues == []`（出力成果物バリデーション不備なし）
4. **Review 要因の排他性**:
   - 発生している `issues`（またはメッセージ）が以下のみで構成されていること：
     - `Unassigned Files (...)`
     - 未割当ファイルの存在に伴う確信度・品質低下ペナルティ（`Album confidence too low`, `Data quality too low`, `Mapping confidence too low`, `LLM's decision (Low Confidence/Ratio)`）
     - バリアント解決済みの中間スロット警告（`Intermediate contradictory slot assignments resolved by variant adoption`）
   - 以下の「本編欠損・異常」を示す要因が 1 つも含まれていないこと：
     - `Steam Tracklist Missing`, `Steam Slots Missing`, `Steam Slots Unexpected`, `Output Track Count Mismatch`
     - `CRITICAL: Audio Source Error`, `Audio quality warning`
     - `Track#0`, `Unknown Title`, `Official Title Mismatch`, `Duplicates`, `Duplicate Output Paths`

---

## 3. 実装方針

1. **`src/sst/validator.py`**:
   - `ResultValidator.validate` において、上記条件を判定するヘルパーロジックを実装。
   - `diagnostics["review_sub_status"] = "BONUS_OR_SE_ISOLATED"` を設定。
2. **`src/sst/processing/package_metadata.py`**:
   - `build_album_summary_metadata` において、`metadata["audit"]["review_sub_status"]` および `metadata["review_sub_status"]` に設定。
3. **`src/sst/processor.py`**:
   - サブステータス付与時にログに明記：
     `[Review: BONUS_OR_SE_ISOLATED] 本編全 {adopted}/{expected} スロット充足、余剰ファイル {unassigned} 件を隔離`
4. **`src/sst/batch_report.py` & `src/sst/report_generator.py`**:
   - ステータスバッジやレポート一覧で `REVIEW (BONUS_OR_SE_ISOLATED)` と明記。
5. **`src/sst/processor_support.py`（通知）**:
   - Discord 通知等のタイトルやサマリーに `[Review: BONUS_OR_SE_ISOLATED]` を反映。

---

## 4. 影響範囲と安全性

- 本ステータスは `review` の分類（サブステータス）であり、`archive` への強制変更ではないため、S.S.T の厳格なバリデーション原則（未割当ファイルがある場合は archive に入れず review に送る）を一切破壊しない。
- 監査者は `BONUS_OR_SE_ISOLATED` のついたアルバムについて、本編ファイルが完全に整理・エンコードされていることを確信して安心して手動確認・ライブラリ採用を行うことができる。
