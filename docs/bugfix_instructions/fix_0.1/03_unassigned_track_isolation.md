# 修正指示書 03: 未割当（Unassigned）トラックの本編採用除外と `review_candidates/` への完全分離

## 1. 背景と問題の概要

現在、Steamスロットに割り当てられなかった未割当（Unassigned）トラックが、`build_slot_variant_index` と `adopt_best_file_per_slot` を経て **本編トラック（`adopted_files` → `disc_N/` 配下の出力および `processed_tracks_meta`）に無条件で採用** されており、同時に `select_best_unassigned_files` によって `review_candidates/` にも重複出力されている。

その結果、本編に出力された未割当トラックがフォールバックのトラック番号（`DEFAULT_PLACEHOLDER` による `"1"` やローカルのトラック番号）を与えられ、**本来正常にマッピングされた本編トラックと衝突して大量の偽陽性エラー（`Duplicates`, `Output Track Count Mismatch`, `Steam Slots Unexpected`, `Official Title Mismatch`）を引き起こしている**。

### 発生している現象（実データ例）
- **AppID `1879310` (TCSTRIKERS4 original soundtrack)**:
  - Steamの32スロットは全曲（`32/32`）正常にマッピングされている（`Alignment slots count=32`）。
  - ローカルにはSteamトラックリストに載っていないボーナストラックが10曲（`unassigned_files=10`）存在する。
  - 現行コードはこの未割当10曲を本編 `adopted_files` にも採用してしまうため、最終トラック数が `42/32` となり、`Steam Slots Unexpected (10)` および `Output Track Count Mismatch (42/32)` が発火して本編 `disc_1/` が42曲に汚染されている。
- **AppID `1621040` (HUNTDOWN)** / **AppID `1761580` (Mayhem Brawler)** / **AppID `2337040` (Wall World)** / **AppID `689920` (1bitHeart)** / **AppID `1851920`** / **AppID `2339210`** / **AppID `2943720`** / **AppID `3162910`** / **AppID `4206020`**:
  - いずれも未割当となったファイルが本編 `tracks` に採用された上で、`review_candidates/` にも出力される二重構造となっており、本編側で `track_number = "1"` 等にフォールバックして `Duplicates` や `Official Title Mismatch` を二次発生させている。

---

## 2. 原因箇所と現行コードの欠陥

### 2.1 `src/sst/processing/slot_variants.py` (`build_slot_variant_index`: 121〜148行目)
```python
        if (
            inferred_slot_key is not None
            and title_matches_steam
            and inferred_slot_key not in slot_variants
        ):
            slot_key = inferred_slot_key
        else:
            slot_key = (disc, clean_title)
        slot_variants[slot_key].extend(variants)
        track_to_slot[track_id] = slot_key
```
Steamスロットに一致しなかったトラックに対し、非数値タプル `slot_key = (disc, clean_title)`（例: `(1, "menu whoosh::sfx1")`）をキーとして `slot_variants` に登録している。

### 2.2 `src/sst/processing/file_selection.py` (`adopt_best_file_per_slot`: 8〜41行目)
```python
def adopt_best_file_per_slot(
    track_groups: Dict,
    slot_variant_index: Dict[tuple[int, str], List[Dict[str, Any]]],
    track_to_slot_index: Dict[str, tuple[int, str]],
) -> Dict[tuple[int, str], Dict[str, Any]]:
    """Select exactly one highest-Tier physical file for each aligned slot."""
    ...
    for slot_key, variants in slot_variant_index.items():
        if not variants:
            continue
```
Docstringには `Select exactly one highest-Tier physical file for each aligned slot.`（アライメント済みスロットごとに最高Tierの物理ファイルを1つ選択する）と明記されているにもかかわらず、`slot_key` がアライメント済みの有効なスロット（`isinstance(slot_key, tuple) and len(slot_key) == 2 and str(slot_key[1]).isdigit()`）であるかのチェックが欠落している。
（※なお、同ファイル内の79〜80行目および92〜93行目の `select_best_unassigned_files` では `if isinstance(slot_key, tuple) and len(slot_key) == 2 and str(slot_key[1]).isdigit():` によってアライメント済みスロットか否かを正しく判定している。）

### 2.3 `src/sst/processing/file_selection.py` (`select_best_unassigned_files`: 86〜95行目)
```python
    for (disc, clean_title), variants in track_groups.items():
        track_id = f"{disc}_{clean_title}"
        if track_id in final_metadata or not variants:
            continue

        if track_to_slot_index and track_id in track_to_slot_index:
            slot_key = track_to_slot_index[track_id]
            if isinstance(slot_key, tuple) and len(slot_key) == 2 and str(slot_key[1]).isdigit():
                continue
```
88行目で `if track_id in final_metadata:` としているが、もし `final_metadata[track_id]` に `matched_v_idx` も `override_track` も設定されていないエントリ（例: `{"action": "use_local_tag"}` 等）が存在した場合、`slot_key` が非数値（未割当）であっても `select_best_unassigned_files` から漏れてしまう。また、`unassigned_file_ids`（`alignment_res["unassigned_files"]`）が渡された場合（96〜99行目）に、`alignment_res["unassigned_files"]` が空リスト `[]` ではなく、後段の `reject_contradictory_slot_assignments` 等で未割当になったトラックが `unassigned_file_ids` に含まれていないと、`variants` がフィルタされて `unassigned_manifest` から漏れるケースがある。

---

## 3. 具体的な修正仕様

### 3.1 `adopt_best_file_per_slot` (`src/sst/processing/file_selection.py`) の修正
1. スロット判定ヘルパー関数 `_is_aligned_slot_key(slot_key: Any) -> bool` を定義する：
   ```python
   def _is_aligned_slot_key(slot_key: Any) -> bool:
       return (
           isinstance(slot_key, tuple)
           and len(slot_key) == 2
           and str(slot_key[1]).isdigit()
           and int(str(slot_key[1])) > 0
       )
   ```
2. `adopt_best_file_per_slot` のループ先頭（22行目付近）で、`not _is_aligned_slot_key(slot_key)` のエントリをスキップする：
   ```python
   for slot_key, variants in slot_variant_index.items():
       if not variants or not _is_aligned_slot_key(slot_key):
           continue
   ```
   これにより、`build_slot_variant_index` の戻り値契約（未割当グループが `(disc, clean_title)` として `slot_variant_index` に含まれること）を維持したまま、本編 `adopted_files` にはアライメント済みの正規スロットのみが採用される。

### 3.2 `select_best_unassigned_files` (`src/sst/processing/file_selection.py`) の修正
1. 88行目の `if track_id in final_metadata or not variants:` を修正し、`track_to_slot_index` が渡されている場合は `track_to_slot_index.get(track_id)` が `_is_aligned_slot_key(slot_key)` であるかどうかを正本として判定する。`track_to_slot_index` が渡されていない場合のみ、`final_metadata.get(track_id)` に有効な `matched_v_idx` または `override_track` が存在するかをチェックする：
   ```python
   if not variants:
       continue
   if track_to_slot_index is not None:
       slot_key = track_to_slot_index.get(track_id)
       if _is_aligned_slot_key(slot_key):
           continue
   else:
       instr = final_metadata.get(track_id) if isinstance(final_metadata, dict) else None
       if isinstance(instr, dict) and (
           instr.get("matched_v_idx") is not None or instr.get("override_track") not in (None, "", "0")
        ):
           continue
   ```
2. 96〜99行目の `if unassigned_file_ids is not None:` フィルタについて：
   `slot_variant_index` および `track_to_slot_index` が与えられている場合、どの `aligned_slot_key` にも属さない `track_id`（かつ `assigned_file_ids_in_slots` に含まれない `file_id`）はすべて実質的な未割当ファイルである。`alignment_res["unassigned_files"]` に一部の `file_id` しか入っていなかった場合でも、アライメント済みスロットに採用されなかった未割当グループが欠落しないよう、`slot_variant_index` / `track_to_slot_index` が指定されているときは `assigned_file_ids_in_slots` による除外（101〜104行目）を優先し、`unassigned_file_ids` の部分集合フィルタによって未割当トラックを取りこぼさないようにする（ただし `slot_variant_index` が `None` の単体呼び出し時は従来通り `unassigned_file_ids` でフィルタする）。

---

## 4. 不変条件・禁止事項

- **未割当ファイルが存在するアルバムを Archive に昇格させてはならない**：
  `adopted_files` から未割当トラックを除外しても、`unassigned_manifest` にはその未割当トラックが必ず記録され、`ResultValidator.validate` の106〜108行目（`if actual_unassigned: issues.append(f"Unassigned Files ({len(actual_unassigned)})")`）によって確実に **Review** へ送られることを保証すること。
- `build_slot_variant_index` 自体の戻り値から `(disc, clean_title)` を削除しないこと（既存テスト `test_unaligned_filename_number_does_not_override_steam_title` が `assert (1, "menu whoosh::sfx1") in slot_variants` を検証しているため）。

---

## 5. テスト作成指示

`tests/test_batch_accuracy_improvements.py` に以下のテストを追加すること。

1. **`test_adopt_best_file_per_slot_excludes_unaligned_tracks_and_routes_to_unassigned`**:
   - **設定**: Steam 2スロット（Track 1 `"Opening"`, Track 2 `"Ending"`）に対し、ローカルに3トラック（`"01 Opening.wav"`, `"02 Ending.wav"`, `"99 Bonus Unused.wav"`）が存在し、`final_metadata` は Track 1, 2 のみをマッピングしているケース（AppID `1879310` / `2337040` 型）。
   - **検証**:
     1. `slot_variant_index, track_to_slot = build_slot_variant_index(final_metadata, track_groups, steam_meta)` を実行。
     2. `adopted = adopt_best_file_per_slot(track_groups, slot_variant_index, track_to_slot)` の件数が **`2`件** であり、`"99 Bonus Unused.wav"` が `adopted` に含まれないこと。
     3. `unassigned = select_best_unassigned_files(track_groups, final_metadata, slot_variant_index=slot_variant_index, track_to_slot_index=track_to_slot)` の件数が **`1`件** であり、`"99 Bonus Unused.wav"` が含まれること。
     4. `ResultValidator.validate` に2件の `tracks` と1件の `unassigned_manifest` を渡した際、`Output Track Count Mismatch` や `Steam Slots Unexpected` や `Duplicates` は発生せず、`Unassigned Files (1)` のみを理由として正しく `status == "review"` になること。

---

## 6. 完了条件・検証コマンド

```bash
rtk uv run pytest tests/test_batch_accuracy_improvements.py tests/test_fast_track.py tests/test_batch_edge_cases.py
rtk uv run pytest
```
すべての既存テストおよび新規追加テストがパスすること。
