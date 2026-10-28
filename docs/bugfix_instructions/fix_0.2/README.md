# S.S.T ロジック欠陥修正・実装指示書一覧 (fix_0.2)

本ディレクトリには、全352件（Archive 270件 / Review 82件、2026-10-28 バッチ処理完了分）の全件突合監査および出力音源・中間ログ（`sst-work/`）・現行コードベースの精査により特定された **6件の重大ロジック・システム処理欠陥** に対する詳細修正作業指示書（回帰テスト作成指示を含む）を格納しています。

---

## 監査サマリ（全352件の内訳）

| 区分 | 件数 | 監査結果の内訳 |
| :--- | :---: | :--- |
| **Archive** | **270件** | ・**正常 Archive**: **269件**（全スロット充足・未割当0件・音源尺/タグ整合を確認）<br>・**問題のある Archive（誤Archive・曲入れ替わり）**: **1件**（AppID `2086480`: Disc 2 Track 34と35が逆のスロットに格納 → **指示書 06** で修正） |
| **Review** | **82件** | ・**正当な Review（仕様通りの隔離）**: **15件**<br>　- 音声変換クリッピング/品質警告: 3件（`457840`, `459851`, `1270860`）<br>　- 元音源ファイル破損（デコード不能）: 1件（`2410560` Track 54）<br>　- Steamトラックリスト未登録・音源0件: 1件（`870530`）<br>　- Steam未掲載の真正ボーナストラック・効果音同梱: 10件（`584382`, `698890`, `1075710`, `1299740`, `1553350`, `1770530`, `1806720`, `2198580`, `2260070`, `3107200` ※うち6件は下記のシステムバグも併発）<br>・**問題のある Review（ロジック・システム処理起因の誤Review）**: **67件**（＋上記ボーナストラック同梱アルバム内の本編スロット欠損6件 → **指示書 01〜06** で修正） |

---

## 指示書一覧と対象範囲

| 通し番号 | ファイル名 | 対象となる欠陥・問題 | 主な変更対象ファイル | 影響を受ける実データ例（AppID） |
| :--- | :--- | :--- | :--- | :--- |
| **01** | [01_slot_variants_and_bilingual_dedup.md](./01_slot_variants_and_bilingual_dedup.md) | 2言語フォルダ（日/英）・同一フォーマット重複・1文字タイポにおけるフォーマットバリアント統合漏れ（`Unassigned Files` 大量発生） | `src/sst/processing/slot_variants.py`<br>`src/sst/processing/duplicate_mappings.py` | Review 26件: Capcom Arcade Stadium 19件 (`1611180`〜`2093740`), `1971340`, `5172510`, `530490`, `630380`, `2294270`, `916190`, `3449720` |
| **02** | [02_duplicate_mappings_destructive_eviction.md](./02_duplicate_mappings_destructive_eviction.md) | `resolve_duplicate_mappings`（`_resolve_disc_title_matches`）における `s_idx != v_idx` 強制退去による正常スロットの上書き破壊・曲入れ替わり | `src/sst/processing/duplicate_mappings.py` | Review 3件（本編スロット破壊）: `916190` (CrossCode), `3449720` (都市伝説解体センター), `467870` (MINUS ZERO) |
| **03** | [03_prematch_and_unassigned_reconciliation.md](./03_prematch_and_unassigned_reconciliation.md) | タグ無しWAVとタグ有りMP3/FLACのプレマッチ自己衝突破棄・トラック番号欠落時の完全一致プレマッチ未対応・残差確定の前方一致横取り・全スロット確定時の確信度未昇格 | `src/sst/llm/prematch.py`<br>`src/sst/processing/unassigned.py`<br>`src/sst/llm/organizer.py` | Review 18件+: `2198580`, `2125650`, `1586580`, `3162910`, `2943720`, `1593020`, `3994280`, `4284690`, `2716920`, `1940590`, `1940600`, `1921810`, `461050`, `865290`, `1568690`, `942070`, `1832420`, `1553350` |
| **04** | [04_llm_phase2_payload_and_slot_resolution.md](./04_llm_phase2_payload_and_slot_resolution.md) | LLM Phase 2 ペイロードからの `dur` / `n` 欠落、チャンク相対番号と `fallback_index = value - 1` による無関係スロットへの誤集約、マルチフォーマット時の `len(steam_matches) == 1` 全棄却バグ | `src/sst/llm/organizer.py`<br>`src/sst/llm/normalization.py`<br>`src/sst/llm/assignment_validation.py`<br>`src/sst/llm/prompts.py` | Review 25件+: `336870`, `354350`, `441260`, `441950`, `442101`, `466530`, `566260`, `802640`, `840070`, `959840`, `1075710`, `1167720`, `1761580`, `1806720`, `1851920`, `1879310`, `1919620`, `2337040`, `2353511`, `3638290` 他 |
| **05** | [05_title_normalization_and_disc_track_extraction.md](./05_title_normalization_and_disc_track_extraction.md) | アポストロフィ空白化・複合語スペース差、`01 - 02 -` 空白付き複合ディスク番号・ファイル名先頭 `Disc N`・連番サブフォルダ `01. Base_ver`・`1bit` 先頭数字誤抽出 | `src/sst/track_grouper.py` | Review 12件: `802640`, `2150000`, `2198580`, `924331`, `1919620`, `2125650`, `1831430`, `1899360`, `689920`, `2716920`, `3107200`, `461050`, `865290` |
| **06** | [06_fast_track_and_validator_cross_slot_guard.md](./06_fast_track_and_validator_cross_slot_guard.md) | Fast-Trackにおける `(Extended Ver.)` 等の汎用接尾辞ストップワード漏れによる別曲スワップ誤Archive（`2086480`）と、`MBZ_STEAM_VERIFIED` における `ResultValidator` の誤検出（`355890`） | `src/sst/processing/fast_track.py`<br>`src/sst/validator.py` | Archive 1件（曲入れ替わり）: `2086480`<br>Review 1件（誤検出）: `355890` |

---

## 推奨作業順序と並行作業の境界

1. **Step 1（基盤正規化・ファイル名解析）**:
   - **指示書 05**（`src/sst/track_grouper.py`）を最初に実施する。タイトル正規化（アポストロフィ除去・英数字プレフィックス除去）とディスク/トラック番号抽出の修正は、後続すべてのプレマッチ・バリアント統合の前提となる。
2. **Step 2（重複解消・バリアント統合層の修正）**:
   - **指示書 01**（`slot_variants.py` / `duplicate_mappings.py`）と **指示書 02**（`duplicate_mappings.py`）は `src/sst/processing/duplicate_mappings.py` を共有するため、**01 → 02 の順で直列**に実施する。
3. **Step 3（プレマッチ・LLM Phase 2・残差確定層の修正）**:
   - **指示書 03**（`prematch.py` / `unassigned.py` / `organizer.py`）と **指示書 04**（`organizer.py` / `normalization.py` / `assignment_validation.py` / `prompts.py`）は `src/sst/llm/organizer.py` を共有するため、**03 → 04 の順で直列**に実施する。
4. **Step 4（Fast-Track・Validator層の修正）**:
   - **指示書 06**（`fast_track.py` / `validator.py`）は編集対象ファイルが独立しているため、Step 1完了後にいつでも（Step 2/3と並行でも）実施可能。

---

## 全担当者共通の不変条件（Critical Rules）

1. **Steamライブラリ内の元ファイル（`/mnt/windows/win_steamlib`）は常に Read-Only** で扱うこと。
2. 現行仕様の正本は [`docs/METADATA_SOURCE_SPEC.md`](../METADATA_SOURCE_SPEC.md) であり、設計判断は必ずこれに従うこと。
3. **STEAMを構造（Disc番号・Track番号・Track Title・総スロット数）の絶対的な正**とし、その不備に対してのみ他ソース（`MBZ_STEAM_VERIFIED` 等）とLLMを使うこと。
4. **LLMはファイルをSTEAMスロットに割り当てる判断者**であり、タイトル生成やタグ値創作をしてはならない。
5. **検証を弱めないこと**：未割当、スロット欠落、範囲外スロット、タイトル矛盾、音声異常、Preflight不一致を Archive へ昇格させてはならず、確証不足の結果は必ず `review` に送ること。
6. 実データ、実ログ、キャッシュ、実音源をテストfixtureへコピーしないこと（テストはすべて `tmp_path` またはメモリ上の合成データで作成すること）。
7. コマンド実行時は `rtk uv run pytest ...` を使用すること。
8. 変更を加えた場合は [`CHANGE_HISTORY.md`](../../CHANGE_HISTORY.md) の先頭（注記の直後）へ新しい順（時系列降順）に日本語で追記すること。

