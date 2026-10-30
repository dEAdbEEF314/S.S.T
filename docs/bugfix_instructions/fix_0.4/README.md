# S.S.T 全件処理後 監査に基づく是正作業指示書一式 (fix_0.4)

## 概要

本ディレクトリには、`fix_0.3` 適用後の音源ライブラリ全352件のバッチ処理結果（SQLite状態DB `data/sst_local_state.db`、実行ログ `logs/SST_DEBUG_*.log`、中間生成物 `sst-work/`、および出力パッケージ `output/{archive,review}/*.zip`）に対する全数フォレンジック監査に基づき、**過剰検知による誤Review送り（23件）の解消**、および**過去の修正で混入した個別事案向けハードコードの根絶と汎用化**を目的とした修正作業指示書（01〜04）を格納しています。

---

## 全352件の監査結果サマリ

| 区分 | 件数 | 内訳と評価 |
| :--- | ---: | :--- |
| **Archive** | **322件** (91.5%) | ・**健全なArchive: 322件（100%健全・誤Archive 0件）**<br>ZIPファイル物理実在、曲数100%一致、Preflight検証通過、重複トラック・未割当混入0件。<br>`4206020`（逆順入れ替わり防止）および `1832420`（同一埋め込みタイトル誤充填防止）の正常隔離を確認済み。 |
| **Review** | **30件** (8.5%) | ・**正当な仕様隔離（Review維持）: 7件**<br>　- 音声クリッピング/品質警告（`457840`, `459851`, `1270860`）<br>　- ソース音声物理破損（`2410560`）<br>　- Steamトラックリスト0件（`870530`）<br>　- 仕様外のボーナストラック（`584382`, `3107200`）<br>・**過剰検知・システム要因による誤Review（是正対象）: 23件**<br>　- `ResultValidator` の過剰クロススロット検知（**20件**: DJMAX 13作品、TRIZEAL、BLUE REVOLVER、Katana ZERO 等）<br>　- LLM JSON レスポンスの重複キー上書き消失（**1件**: `466530` Koihime Enbu）<br>　- フラットフォルダ通し連番のマルチディスクバリアント統合不全（**2件**: `1879310` TCSTRIKERS4, `2943720` A_25 番号抽出） |

---

## 修正指示書一覧

| 順序 | 指示書ファイル | 対象モジュール | 主な解決対象 |
| :---: | :--- | :--- | :--- |
| **1** | [01_validator_cross_slot_accuracy_and_subtitles.md](01_validator_cross_slot_accuracy_and_subtitles.md) | `src/sst/validator.py` | `ResultValidator` において、自スロット適合（`matches_assigned`）を先行判定し、括弧除去タイトル（Extended Ver. や Remix 等）がアルバム内の原曲スロットと衝突して誤爆する過剰検知を防止（誤Review 20件を解消）。真の入れ替わり（`4206020`型）は確実に検知。 |
| **2** | [02_remove_hardcoded_typo_replacements.md](02_remove_hardcoded_typo_replacements.md) | `src/sst/track_grouper.py`<br>`src/sst/llm/prematch.py` | 個別AppID（1167720）向けのハードコード `artifical -> artificial` を完全削除し、既存の類似度計算（`SequenceMatcher >= 0.88`）に汎用統合。単一文字ディスク/セクション記号（`A_25_...`）のトラック番号抽出を一般化。 |
| **3** | [03_llm_json_duplicate_key_merging.md](03_llm_json_duplicate_key_merging.md) | `src/sst/llm/response_parser.py` | LLMが同一スロットキーを複数回出力した場合に、Python標準 `json.loads` の後勝ちで有効なマッピングが空配列 `{"files": []}` で破棄されるのを防止する `object_pairs_hook` カスタムマージを実装（`466530` を解消）。 |
| **4** | [04_multidisc_continuous_numbering_variant_consolidation.md](04_multidisc_continuous_numbering_variant_consolidation.md) | `src/sst/processing/slot_variants.py` | 単一フラットフォルダ内に通し連番（例: Disc 2 track 20）で同居する異フォーマット（WAV/MP3）の兄弟バリアントについて、推定disc不一致でも同一トラック番号・同一ステム・尺整合に基づき安全にバリアント統合（`1879310` を解消）。 |

---

## 厳守すべき設計原則（[docs/METADATA_SOURCE_SPEC.md](../../docs/METADATA_SOURCE_SPEC.md) 準拠）

1. **Steam ライブラリ内の元ファイルは常に Read-Only** で扱うこと。
2. **STEAM を構造（曲数・曲順・ディスク構成・公式タイトル）の絶対的な正**とし、その不備に対してのみ他ソースと LLM を使うこと。
3. **LLM はファイルを STEAM スロットに割り当てる判断者**であり、タイトル生成やタグ値創作をしてはならない。
4. **確証不足の結果は archive ではなく review に送ること**。
5. **個別事案向けハードコードの禁止**: タイポ修正や特定AppID向けの文字列置換を個別ロジックとして埋め込まず、類似度判定や規則的な正規化ルールとして汎用化すること。

