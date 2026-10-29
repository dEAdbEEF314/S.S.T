# S.S.T バッチ処理結果 監査に基づく修正作業指示書一式 (fix_0.3)

## 概要

本ディレクトリには、`fix_0.2` 適用後の全352件バッチ処理結果（`data/sst_local_state.db`、実行ログ `logs/SST_DEBUG_20261029064219.log`、中間生成物 `sst-work/`、および最終パッケージ `output/{archive,review}/*.zip`）に対する全数フォレンジック監査に基づき、**ロジックの欠陥やシステム不備によって誤って Archive または Review 送りとなったケース**を根絶するための詳細修正作業指示書（01〜06）を格納しています。

---

## 全352件の監査結果サマリ

| 区分 | 件数 | 内訳と評価 |
| :--- | ---: | :--- |
| **Archive** | **324件** (92.0%) | ・**正常Archive: 321件**（スロット充足率・最上位フォーマット選択・公式タイトル一致・再生時間整合すべて完全）<br>・**問題のあるArchive（要修正）: 2件**（AppID `4206020` [0始まり番号ズレ＋LLM逆順誤割当＋Validator見逃し]、AppID `1832420` [同一埋め込みタイトルの重複Track 11ファイル衝突見逃し＋Slot 12誤充填]）<br>・**ローカル連番欠番の正常救済: 1件**（AppID `1568690`: ローカル `24` 欠番で `25, 26` が Steam `1_24, 1_25` と曲名・尺完全一致） |
| **Review** | **28件** (8.0%) | ・**正当なReview（仕様通り）: 9件**<br>　- 音声品質警告（クリッピング等）: 3件（`457840`, `459851`, `1270860`）<br>　- ソース音声ファイル物理破損: 1件（`2410560` Track 54）<br>　- Steamトラックリスト不在・0曲: 1件（`870530`）<br>　- 本編100%確定＋純粋な未収録ボーナストラック隔離: 4件（`584382`, `1553350`, `1806720`, `3107200`）<br>・**正当なReview要因＋本編スロットのシステムバグ併発（要修正）: 3件**（`942070`, `1299740`, `1879310`）<br>・**システム・ロジック欠陥による誤Review（要修正）: 16件**（`336870`, `442101`, `466530`, `566260`, `630380`, `689920`, `802640`, `840070`, `959840`, `1167720`, `1851920`, `2260070`, `2943720`, `3162910`, `3638290`, `3994280`） |

---

## 修正指示書一覧と優先実装順序

各指示書は独立したモジュール単位で記述されていますが、データフローの上流（正規化・番号抽出 → プレマッチ → LLM Phase 2 → 矛盾排除 → バリアント統合・残差確定 → 最終バリデータ）に沿って以下の順序で実装・テストすることを推奨します。

| 順序 | 指示書ファイル | 対象モジュール | 主な解決対象（該当AppID） |
| :---: | :--- | :--- | :--- |
| **1** | [03_title_normalization_and_track_number_extraction.md](file:///mnt/workspace/S.S.T/docs/bugfix_instructions/fix_0.3/03_title_normalization_and_track_number_extraction.md) | `src/sst/track_grouper.py`<br>`src/sst/llm/prematch.py`<br>`src/sst/steam_web_api.py` | ・NFKC正規化によるアキュートアクセント（`´` U+00B4）の空白分裂バグ（`802640`）<br>・アンダースコア識別子（`radio1_8.mp3`）からの誤ったトラック番号抽出（`1851920`）<br>・単一フォルダ通し連番WAV（`20..32`）とマルチディスクSteam定義（Disc 2 `1..13`）のグローバル連番照合（`1879310`）<br>・Steam PICS `originalname` 内の改行CSV混入によるトラック結合破損の分割復元（`1299740`） |
| **2** | [04_offset_numbered_and_unnumbered_prematch.md](file:///mnt/workspace/S.S.T/docs/bugfix_instructions/fix_0.3/04_offset_numbered_and_unnumbered_prematch.md) | `src/sst/llm/prematch.py`<br>`src/sst/llm/organizer.py` | ・ローカル番号とSteamスロット番号にオフセット・入れ替わりがあるアルバム（0始まり連番、欠番シフト、タグ番号ズレ）におけるアルバム全体1対1厳密タイトル＋尺一致プレマッチ（`4206020`, `2943720`, `3994280`, `942070`, `1299740`）<br>・`_recover_prematch_fallback_slots` における明示的番号プレフィックス不一致（`03_` vs `01_`）時の誤フォールバック防止（`2943720`） |
| **3** | [01_llm_phase2_prompt_and_chunk_key_resolution.md](file:///mnt/workspace/S.S.T/docs/bugfix_instructions/fix_0.3/01_llm_phase2_prompt_and_chunk_key_resolution.md) | `src/sst/llm/organizer.py`<br>`src/sst/llm/prompts.py`<br>`src/sst/llm/normalization.py` | ・Phase 2のプロンプト切り替え（複合キー `<d>_<n>` 必須化と旧キャッシュ無効化）<br>・チャンク分割時の異フォーマットペア（FLAC+MP3等）分断防止<br>・部分リスト（`unfilled_steam_slots`）に対する `v_idx` 0始まり衝突・相対連番キーの誤解決防止と `reason` 整合検証（`336870`, `442101`, `466530`, `566260`, `630380`, `689920`, `840070`, `959840`, `1832420`, `1879310`, `2260070`, `3162910`, `3638290`, `3994280`） |
| **4** | [02_contradictory_slot_retention_by_number_and_duration.md](file:///mnt/workspace/S.S.T/docs/bugfix_instructions/fix_0.3/02_contradictory_slot_retention_by_number_and_duration.md) | `src/sst/llm/assignment_validation.py` | ・`reject_contradictory_slot_assignments` において、別チャンクからの誤割当が衝突した際に、スロットの `(disc, n)` と再生時間（±3.0秒以内）が完全一致する正当な多言語・異フォーマットトラック群まで巻き添えで全没収される問題の修正（`336870`, `442101`, `466530`, `566260`, `630380`, `840070`, `959840`）<br>・助詞1文字差（`は` vs `が`）のタイトル互換判定強化（`630380`） |
| **5** | [05_slot_variants_and_embedded_title_consolidation.md](file:///mnt/workspace/S.S.T/docs/bugfix_instructions/fix_0.3/05_slot_variants_and_embedded_title_consolidation.md) | `src/sst/processing/slot_variants.py`<br>`src/sst/processing/unassigned.py`<br>`src/sst/llm/prematch.py` | ・Steamタイトルのカテゴリ接頭辞（`ME 01 - Quest`）・`(unused)` 表記・同名連番スロット（`Dungeon - Artificial` ×3）に対するプレマッチおよびタグなしWAV＋タグ付きMP3統合（`1167720`）<br>・70%以上のスロットが決定論的に確定済みのアルバムにおける、残余空きスロットと同一 `(disc, n)` かつ再生時間一致（±2.0秒以内）の未割当バリアント群の構造的確定（Pass 3）（`2260070`, `3162910`, `336870`, `442101`, `466530`, `566260`, `840070`, `959840`） |
| **6** | [06_validator_cross_slot_and_prematch_collision_guard.md](file:///mnt/workspace/S.S.T/docs/bugfix_instructions/fix_0.3/06_validator_cross_slot_and_prematch_collision_guard.md) | `src/sst/processor_tracks.py`<br>`src/sst/validator.py`<br>`src/sst/llm/prematch.py` | ・`processor_tracks.py` における `original_embedded_title` / `clean_title` 出力と、`ResultValidator` における括弧付きサブタイトル（`(New Tokyo)` 等）除去後のクロススロット不一致検出（`4206020` 誤Archive阻止）<br>・`extract_deterministic_prematches` における `norm_stem` 乖離検査による同一埋め込みタイトル別曲の衝突検出（`1832420` 誤Archive阻止） |

---

## 厳守すべき設計原則（[docs/METADATA_SOURCE_SPEC.md](file:///mnt/workspace/S.S.T/docs/METADATA_SOURCE_SPEC.md) 準拠）

1. **Steam ライブラリ内の元ファイルは常に Read-Only** で扱うこと。
2. **STEAM を構造（曲数・曲順・ディスク構成・公式タイトル）の絶対的な正**とし、その不備に対してのみ他ソースと LLM を使うこと。
3. **LLM はファイルを STEAM スロットに割り当てる判断者**であり、タイトル生成やタグ値創作をしてはならない。
4. **確証不足の結果は archive ではなく review に送ること**。バリデータの閾値緩和やエラー握り潰しによる見せかけの Archive 率向上は厳禁とする。
5. コード変更時は必ず [CHANGE_HISTORY.md](file:///mnt/workspace/S.S.T/CHANGE_HISTORY.md) の先頭（時系列降順）に日本語で変更履歴を追記すること。

