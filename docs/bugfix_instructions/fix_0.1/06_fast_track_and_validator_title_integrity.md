# 修正指示書 06: Fast-Trackのタイトル不一致フォールバック廃止と `ResultValidator` 公式タイトル整合性検証の実効化

## 1. 背景と問題の概要

S.S.T の品質保証ゲートにおいて、以下の2つの構造的抜け穴（ロジック欠陥）が存在する。

1. **Fast-Track（LLM/APIバイパス経路）における番号のみフォールバックの抜け穴**:
   `build_fast_track_group_map`（`src/sst/processing/fast_track.py`）は、81〜94行目でSteamタイトルとローカルタイトルの一致を確認しているが、**タイトルが不一致だった場合でも、96〜97行目で無条件にトラック番号のみで `slot_key = candidate_slot_key` を採用**している。その結果、ローカルにタイトルが存在し、かつSteamタイトルと全く異なる別曲（例: 0始まりと1始まりのズレや別ディスク曲）であっても、トラック番号が揃っていればタイトル検査を素通りして Fast-Track Archive になり得る。
2. **`ResultValidator.validate` における `Official Title Mismatch` 検査の形骸化（トートロジー）**:
   `ResultValidator.validate`（`src/sst/validator.py` 154〜171行目）は、出力トラックの `track["tags"]["title"]` と `steam_meta.store_tracklist` のタイトルを比較して `Official Title Mismatch` を判定している。
   しかし、前段の `MetadataBuilder.build_tag_map`（`src/sst/builder.py` 87〜88, 136〜138行目）は、**`matched_v_idx` が設定されているすべてのトラックの `tags["title"]` を `steam_meta.store_tracklist[matched_v_idx]["title"]` で上書き**する。
   つまり、`matched_v_idx` が付与されたトラックに対しては、**「Steamからコピーした文字列」と「Steamの文字列」を比較する恒真判定（トートロジー）** になっており、全く別の音源ファイルが誤ったSteamスロットに割り当てられても `Official Title Mismatch` が絶対に発火しない。

---

## 2. 原因箇所と現行コードの欠陥

### 2.1 `src/sst/processing/fast_track.py` (`build_fast_track_group_map`: 81〜100行目)
```python
        if candidate_slot_key is not None and candidate_slot_key in steam_tracks_by_slot:
            steam_track = steam_tracks_by_slot[candidate_slot_key]
            steam_title = TrackManager.normalize_title(
                str((steam_track or {}).get("title") or (steam_track or {}).get("name") or "")
            )
            if not normalized_titles or steam_title in normalized_titles:
                slot_key = candidate_slot_key

        if slot_key is None and steam_meta:
            for normalized_title in normalized_titles:
                title_matches = steam_title_map.get(normalized_title, [])
                if len(title_matches) == 1:
                    slot_key = title_matches[0]
                    break

        if slot_key is None and candidate_slot_key is not None and candidate_slot_key in steam_tracks_by_slot:
            slot_key = candidate_slot_key
```
- 96〜97行目が無条件で `slot_key = candidate_slot_key` を代入しているため、81〜94行目のタイトル照合が失敗してもすべて上書き通過してしまう。
- なお、実際の健全なArchiveアルバムには、ファイル名が短縮形・スペースなし・内部ID（例: `01 BurgerShop.flac` vs Steam `"Burger Shop Theme"`、`001_coin.flac` vs 埋め込みタグ `"COIN SE"`、`04 - Enough About That! - Stage Clear.flac` vs `"そんなことより！ StageClear"`）のケースがある。したがって、86行目のタイトル一致判定を適切に拡張（スペース除去比較や部分トークン一致、あるいはローカルファイル名が汎用トラック名 `Track 01` 等の場合の扱い）した上で、**ローカルタイトルとSteamタイトルが明確に別曲を指して矛盾している場合（例: ローカル `"1. THE FINAL STAND"` vs Steam Slot 1 `"Rebal"`）には Fast-Track を成立させず `return None`（LLM経路へ委譲）** にする必要がある。

### 2.2 `src/sst/processor_tracks.py` & `src/sst/validator.py` (`Official Title Mismatch`: 154〜171行目)
- `process_single_track`（`src/sst/processor_tracks.py` 219〜237行目）が生成する `track_meta` には、出力用の `tags["title"]`（Steamタイトルで上書き済み）と `original_filename` は記録されているが、埋め込みタグの元タイトル（`original_embedded_title`）や、アライメント根拠（`alignment_evidence` / `alignment_reason`）に対するローカルタイトルの検証情報が不足している。
- 特に、`SYSTEM: Number match fallback` のようにタイトル未検証で `matched_v_idx` が付与された場合でも、`tags["title"]` がSteamタイトルで上書きされるため `ResultValidator` が異常を検知できない。

---

## 3. 具体的な修正仕様

### 3.1 `build_fast_track_group_map` (`src/sst/processing/fast_track.py`) の修正
1. **タイトル互換性判定関数 `_fast_track_titles_compatible(normalized_titles: List[str], steam_title: str) -> bool` の導入**:
   - `not normalized_titles` または `not steam_title` の場合は `False` ではなく、トラック番号のみの手がかりしかないケース（例: `01.wav` 等）として扱う。
   - いずれかの `local_title in normalized_titles` について、以下のいずれかが成立すれば互換（`True`）と判定する：
     1. 完全一致または部分包含: `steam_title == local_title` または `steam_title in local_title` または `local_title in steam_title`
     2. スペース除去後の一致または包含（CamelCase・スペース詰めの吸収: 例 `"burgershop"` in `"burgershoptheme"`, `"welcomehomephogs"` == `"welcomehomephogs"`）:
        `s_compact = steam_title.replace(" ", "")`, `l_compact = local_title.replace(" ", "")` において、`len(l_compact) >= 3` かつ（`s_compact == l_compact` または `s_compact in l_compact` または `l_compact in s_compact`）
     3. 単語トークンの有意な重複（例: 英語副題 `"Stage Clear"` / `"Last Boss"` / `"Main Theme"` の共有）。
2. **他スロットのタイトルと完全一致するローカルファイルの誤番号配置の拒否（最優先ガード）**:
   96〜97行目の無条件フォールバックを修正し、もし `normalized_titles` のいずれかが **別のSteamスロット `other_slot_key != candidate_slot_key` のタイトルと一意に一致しているにもかかわらず、`candidate_slot_key` の `steam_title` とは一致しない場合**（例: 0始まりによる1曲ズレで `01_THE_FINAL_STAND` が Slot 2 `"The Final Stand"` ではなく Slot 1 `"Rebal"` を指している場合、またはトラック順序が入れ替わっている場合）は、番号フォールバックを**絶対に行わず**（または `title_matches[0]` を優先し、番号とタイトルがねじれている場合は Fast-Track 自体を `return None` で中止して LLM に委ねる）。

### 3.2 `ResultValidator.validate` (`src/sst/validator.py`) の修正
1. 既存の `Official Title Mismatch` 検査（154〜171行目：出力タグ `tags["title"]` が当該 `(disc, track_number)` の Steam 公式タイトルと一致しているかの Preflight 検査）はそのまま維持する。
2. 追加の物理整合性チェックとして、各トラックの `alignment_reason`（または `track.get("reason")`）およびローカル由来のタイトル（`original_filename` 等）を検査し、もし **`matched_v_idx` が付与されているにもかかわらず、そのトラックの正規化ファイル名/元タイトルが「同一アルバム内の別のSteamスロットの正規化タイトル」と完全一致し、かつ割り当てられたSteamスロットのタイトルとは不一致である場合**（すれ違い・1曲ズレ誤割当）、それを `Official Title Mismatch`（または `Slot Title Cross-Contradiction`）として検出し、確実に `issues` に追加して `status = "review"` とする。
   - 注意: 同一タイトルが複数スロットに存在する正当なケース（例: `"Gear Shift"` が Slot 1 と Slot 2 の両方にある場合）は、割り当て先スロットのタイトルとも一致するため誤検知されない。

---

## 4. 不変条件・禁止事項

- 既存の `tests/test_fast_track.py` に含まれるすべての Fast-Track テストケース（正常な1:1一致、マルチフォーマット統合、HTML実体参照、単曲アルバム、異常番号時のバイパス拒否等）をすべてパスさせること。
- `ResultValidator` の既存の検証項目（`Steam Slots Missing`, `Steam Slots Unexpected`, `Unassigned Files`, `LLM Rejected Slots`, `LLM Duplicate Assignment`, `LLM Contradictory Slot Assignments`, `Track#0`, `Unknown Title`, `Dirty Tags`, `Duplicates`, `Audio Quality Warning`, `CRITICAL: Audio Source Error`）を一切弱めないこと。

---

## 5. テスト作成指示

`tests/test_fast_track.py` および `tests/test_audit_contracts.py`（または `tests/test_batch_accuracy_improvements.py`）に以下のテストを追加すること。

1. **`test_fast_track_rejects_shifted_tracks_where_titles_match_other_steam_slots`**:
   - **設定**: Steamトラックリストが `1: "Rebal"`, `2: "The Final Stand"`, `3: "Contemplation"` に対し、ローカルファイルが `01_The Final Stand.mp3` (`t_num_val="1"`), `02_Contemplation.mp3` (`t_num_val="2"`), `03_Rebal.mp3` (`t_num_val="3"`) のように番号とタイトルがズレているケース。
   - **検証**: `build_fast_track_group_map`（または `_check_fast_track`）が番号だけで誤って Slot 1 に `"The Final Stand"` を割り当てず、Fast-Track 不成立（`None` / `False`）として LLM アライメントへフォールバックすること。
2. **`test_validator_detects_cross_slot_title_misassignment`**:
   - **設定**: Steamトラックリストが `1: "Rebal"`, `2: "The Final Stand"` であり、出力 `tracks` の Slot 1（`disc_number="1/1", track_number="1", title="Rebal"`）の `original_filename` が `"1. THE FINAL STAND.mp3"` である（Slot 2の曲名と完全一致し、Slot 1の曲名 `"Rebal"` と矛盾している）ケース。
   - **検証**: `ResultValidator.validate` が `status == "review"` を返し、`Official Title Mismatch`（または対応する矛盾エラー）を `message` / `issues` に含めること。

---

## 6. 完了条件・検証コマンド

```bash
rtk uv run pytest tests/test_fast_track.py tests/test_audit_contracts.py tests/test_batch_accuracy_improvements.py
rtk uv run pytest
```
すべての既存テストおよび新規追加テストがパスすること。
