# S.S.T ロジック欠陥修正・実装指示書一覧

本ディレクトリには、全352件（Archive 320件 / Review 32件）のバッチ実行結果および現行コードベースの突合監査により特定された **6件の重大ロジック欠陥** に対する詳細修正実装指示書（テスト作成指示を含む）を格納しています。

---

## 指示書一覧と対象範囲

| 通し番号 | ファイル名 | 対象となる欠陥・問題 | 主な変更対象ファイル | 影響を受ける実データ例（AppID） |
| :--- | :--- | :--- | :--- | :--- |
| **01** | [01_multidisc_prematch_and_alignment.md](./01_multidisc_prematch_and_alignment.md) | マルチディスクにおける決定論的プレマッチの別ディスク上書き・LLM Phase 2早期スキップ・重複解消時の生文字列比較 | `src/sst/llm/prematch.py`<br>`src/sst/llm/organizer.py`<br>`src/sst/processing/duplicate_mappings.py` | Review 10件: `2198580`, `1806720`, `2125650`, `1568690`, `459851`, `1621040`, `942070`, `802640`, `856840`, `1796120` |
| **02** | [02_unicode_title_normalization.md](./02_unicode_title_normalization.md) | 非ASCII文字（日本語・韓国語・中国語・キリル文字等）のタイトル全消去と空文字/短語フォールバック誤爆 | `src/sst/track_grouper.py`<br>`src/sst/builder.py`<br>`src/sst/llm/prematch.py` | Review 2件+: `689920`, `1851920`, `2339210` |
| **03** | [03_unassigned_track_isolation.md](./03_unassigned_track_isolation.md) | 未割当（Unassigned）トラックの本編 `adopted_files`（`disc_N/`）への無条件混入と二重出力 | `src/sst/processing/file_selection.py`<br>`src/sst/processing/slot_variants.py` | Review 11件: `1879310`（主因）, `689920`, `1299740`, `1621040`, `1761580`, `1851920`, `2337040`, `2339210`, `2943720`, `3162910`, `4206020` |
| **04** | [04_llm_connection_error_and_fallback.md](./04_llm_connection_error_and_fallback.md) | LLM通信断（`APIConnectionError`）時の誤った「応答切断フォールバック」発動とタイトル未検証の番号のみマッピング | `src/sst/llm/identity.py`<br>`src/sst/llm/organizer.py` | Review 10件: `4206020`, `2943720`, `2339210`, `905290`, `1593020`, `2716920`, `467870`, `584382`, `2455450`, `3282950` |
| **05** | [05_filename_disc_and_track_extraction.md](./05_filename_disc_and_track_extraction.md) | ファイル名からの複合ディスク番号 `^(\d+)[-_](\d+)` 誤爆（`TPOS` 破損）およびアルバム名除去前のトラック番号誤抽出 | `src/sst/track_grouper.py`<br>`src/sst/processing/album_context.py` | Archive 5件（`TPOS` 破損）: `1944840`, `1475790`, `1394870`, `1987320`, `924331`<br>Review 2件: `2339210`, `3162910` |
| **06** | [06_fast_track_and_validator_title_integrity.md](./06_fast_track_and_validator_title_integrity.md) | Fast-Trackにおけるタイトル不一致時の番号フォールバック抜け穴と `ResultValidator` 公式タイトル一致検査の形骸化（トートロジー） | `src/sst/processing/fast_track.py`<br>`src/sst/validator.py`<br>`src/sst/processor_tracks.py` | 全アルバム共通の安全性・完全性ゲート強化 |

---

## 推奨作業順序と並行作業の境界

1. **先行実施（基盤正規化・ファイル名解析）**:
   - **指示書 02**（`TrackManager.normalize_title` のUnicode対応）と **指示書 05**（`TrackManager.build_file_records` のディスク・トラック番号抽出修正）はどちらも `src/sst/track_grouper.py` を編集するため、**同一担当者または直列（02 → 05）**で実施すること。
2. **LLM・アライメント層の修正**:
   - **指示書 01**（マルチディスク・プレマッチ）と **指示書 04**（LLM通信エラー・フォールバック）は `src/sst/llm/organizer.py` を共有するため、**01 → 04 の順で直列**に実施すること（02の `normalize_title` 修正後に実施するとタイトル照合が一貫する）。
3. **ファイル選択・Fast-Track・Validator層の修正**:
   - **指示書 03**（`file_selection.py` / `slot_variants.py`）と **指示書 06**（`fast_track.py` / `validator.py` / `processor_tracks.py`）は編集対象ファイルが独立しているため、**並行実施が可能**。

---

## 全担当者共通の不変条件（Critical Rules）

1. **Steamライブラリ内の元ファイルは常に Read-Only** で扱うこと。
2. 現行仕様の正本は [`docs/METADATA_SOURCE_SPEC.md`](../METADATA_SOURCE_SPEC.md) であり、設計判断は必ずこれに従うこと。
3. **STEAMを構造（Disc番号・Track番号・Track Title・総スロット数）の絶対的な正**とし、その不備に対してのみ他ソース（`MBZ_STEAM_VERIFIED` 等）とLLMを使うこと。
4. **LLMはファイルをSTEAMスロットに割り当てる判断者**であり、タイトル生成やタグ値創作をしてはならない。
5. **検証を弱めないこと**：未割当、スロット欠落、範囲外スロット、タイトル矛盾、音声異常、Preflight不一致を Archive へ昇格させてはならず、確証不足の結果は必ず `review` に送ること。
6. 実データ、実ログ、キャッシュ、実音源をテストfixtureへコピーしないこと（テストはすべて `tmp_path` またはメモリ上の合成データで作成すること）。
7. コマンド実行時は `rtk uv run pytest ...` を使用すること。
8. 変更を加えた場合は [`CHANGE_HISTORY.md`](../../CHANGE_HISTORY.md) の先頭（注記の直後）へ新しい順（時系列降順）に日本語で追記すること。
