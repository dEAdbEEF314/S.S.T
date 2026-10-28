# 修正指示書 01: マルチディスクにおける決定論的プレマッチの衝突解消とLLM Phase 2スキップ条件の修正

## 1. 背景と問題の概要

2枚組以上のマルチディスク・サウンドトラックにおいて、LLM呼び出し前の決定論的プレマッチ（`prematch.py`）と差分推論アライメント（`organizer.py`）、および重複マッピング解消（`duplicate_mappings.py`）に以下の3つの連鎖バグが存在し、**Review行き32件中10件の直接原因**となっている。

### 発生している現象（実データ例）
- **AppID `2198580` (DREDGE - Original Soundtrack)**: Steam 97スロット（Disc 1: 69曲, Disc 2: 11曲, Disc 3: 17曲）。Disc 1およびDisc 2のTrack 1〜17がすべてDisc 3の `3_1`〜`3_17` に決定論的プレマッチで誤確定され、Disc 1の `01 Main Theme.wav` が `3_1 The Iron Rig Theme` として出力された結果、28スロット欠損（`69/97`）でReview行き。
- **AppID `1806720` (Dead Estate)**: Steam 79スロット（Disc 1: 63曲, Disc 2: 16曲）。Disc 1のTrack 1〜16がすべてDisc 2（`2_1`〜`2_16`）に誤確定され、LLM Phase 2がバイパスされた結果、16スロット欠損（`63/79`）。
- **AppID `2125650` (DJMAX Portable 2)** / **AppID `1568690` (DJMAX Portable 3)** / **AppID `459851` (Gremlins, Inc.)**: 同様にDisc 1のトラックがDisc 2の同番号スロットに吸収され、それぞれ22曲・21曲・11曲欠損。
- **AppID `1621040` (HUNTDOWN)**: Disc 1の `01 Prologue.wav`〜`11 Pole Position.wav` がプレマッチでDisc 2（`2_1`〜`2_11`）に誤確定されたため、残ったDisc 2のファイル（`12 A Mother Knows Her Children.wav`〜`21`）をLLMが空いていたDisc 1（`1_1`〜`1_10`）に逆向きに割り当て、Disc 1とDisc 2の曲名が総入れ替わりした。
- **AppID `802640` (Deep Rock Galactic)** / **AppID `856840` (FRAMED Collection)** / **AppID `1796120` (Fights in Tight Spaces)**: 後段の `_resolve_disc_title_matches` が生文字列の `.lower()` で比較しているため、`They're Here!` vs `They're Here`、`Cowards Crossing` vs `Coward's Crossing`、`08 CAST _ CREW` vs `Cast & Crew`、`05 Warrior's Journey` 等の記号・句読点差で救済に失敗し、Disc 2に誤残留してスロット欠損。

---

## 2. 原因箇所と現行コードの欠陥

### 2.1 `src/sst/llm/prematch.py` (`resolve_prematch_signals`: 55〜148行目)
1. **59〜61行目の辞書上書きバグ**:
   ```python
   steam_by_slot_num: Dict[str, Dict[str, Any]] = {
       str(t.get("n")): t for t in full_ref_steam if t.get("n") is not None
   }
   ```
   ディスク番号 `d`（または `disc`）を無視してトラック番号 `n` のみをキーにしているため、マルチディスクでは**最後のディスクのスロットが前のディスクのスロットをすべて上書き**する。
2. **73〜78行目および84〜88行目の `fp_candidate` / `mbz_search_candidate` 検索バグ**:
   `str(fp.get("n")) == str(track_num)` とトラック番号のみで検索しており、ディスク番号やタイトル整合性を確認していない。
3. **98〜103行目および122〜125行目の無条件 `acoustid_match` 確定バグ**:
   `target_slot_num` を `steam_by_slot_num` で引き、タイトルが全く異なる別ディスクのスロットであっても `res.acoustid_steam_slot` と `res.target_v_idx` をセットし、122行目の `if res.acoustid_steam_slot is not None:` でタイトル照合を行わずに `is_deterministic = True` にしている。
4. **128〜129行目のフォールバック上書きバグ**:
   `steam_by_disc_and_track.get((disc_val, str(track_num)))` が見つからない場合に `steam_by_slot_num[str(track_num)]` へフォールバックし、複数ディスクに同じトラック番号が存在する場合でも最終ディスクを単一候補として選択している。

### 2.2 `src/sst/llm/organizer.py` (`LLMOrganizer.align_slots`: 680〜691行目)
```python
if not unmatched_local_tracks or not unfilled_steam_slots:
```
条件が **`or`** になっているため、マルチディスクで全ローカルトラックが最終ディスク等の特定スロットへ多重割当されて `unmatched_local_tracks` が空（`[]`）になった時点で、`unfilled_steam_slots`（未充填のSteamスロット）が大量に残っているにもかかわらず LLM Phase 2 をバイパスして完了扱いにしてしまう。

### 2.3 `src/sst/processing/duplicate_mappings.py` (`_resolve_multidisc_index_conflicts` / `_resolve_disc_title_matches`: 95〜158行目)
1. `_resolve_multidisc_index_conflicts`（114〜115行目）および `_resolve_disc_title_matches`（136, 140〜150行目）が、`TrackManager.normalize_title` を使わずに生の `.lower()` で比較している。また、`tid` に含まれる `::file_id` サフィックスを除去せずに `local_title = tid.split("_", 1)[1].lower()` としているため、`local_title` の末尾に `::0123456789abcdef` が付いたまま比較・`SequenceMatcher` 計算を行っており、完全一致や類似度判定を著しく阻害している。

---

## 3. 具体的な修正仕様

### 3.1 `src/sst/llm/prematch.py` の修正
1. **トラック番号ごとのSteamスロット候補リスト化**:
   単一辞書 `steam_by_slot_num` を廃止し、同じトラック番号を持つ全ディスクのスロットを保持する `steam_slots_by_num: Dict[str, List[Dict[str, Any]]]` を構築する。
   ```python
   steam_slots_by_num: Dict[str, List[Dict[str, Any]]] = {}
   for t in full_ref_steam:
       if t.get("n") is not None:
           steam_slots_by_num.setdefault(str(t.get("n")), []).append(t)
   ```
2. **タイトル整合性ヘルパーの導入**:
   ローカルトラックのタイトル（`track.get("title") or track.get("norm_stem") or ""`）とSteamスロットのタイトル（`steam_slot.get("t") or steam_slot.get("title") or ""`）を `TrackManager.normalize_title` で正規化し、**双方が非空文字であり、かつ完全一致または単語境界を含む部分一致（例: `s_title == l_title or s_title in l_title or l_title in s_title`）** する場合のみタイトル整合（`_titles_match(local_track, steam_slot) -> bool`）と判定する。
   - **重要**: `not s_title or not l_title` の場合（タイトルが空、または正規化で空になった場合）は、トラック番号だけで決定論的確定（`is_deterministic = True`）してはならない（[`docs/METADATA_SOURCE_SPEC.md`](../METADATA_SOURCE_SPEC.md) §7.1 準拠）。
3. **候補スロット解決ロジックの厳格化**:
   `(disc_val, target_slot_num)` で `steam_by_disc_and_track` を引く際も、マルチディスク（または全ディスク共通）で以下のように解決する：
   - Step A: `steam_by_disc_and_track.get((disc_val, target_slot_num))` が存在し、かつ `_titles_match(track, slot)` が真であればそのスロットを採用する。
   - Step B: Step Aで決まらない場合（ローカルが全曲 `disc=1` でフラット配置されているマルチディスク等）、`steam_slots_by_num.get(target_slot_num, [])` のうち `_titles_match(track, slot)` が真となるスロットが **ただ1つ（一意）** 存在する場合に限り、そのスロットを採用する。
   - Step C: 単一ディスク（`len(steam_slots_by_num.get(target_slot_num, [])) == 1` かつアルバム全体の総ディスク数が1）で、かつ `fp_candidate` が `track.get("v_idx")` で直接紐付いている場合でも、ローカルタイトルが非空でSteamタイトルと明確に矛盾する場合は `is_deterministic = True` にしない。
   - `acoustid_match` / `mbz_search_match` においても、上記でタイトル整合が確認された `steam_slot` が見つかった場合にのみ `res.acoustid_steam_slot` / `res.target_v_idx` / `res.is_deterministic = True` を設定する。
4. **同一 `v_idx` への異タイトル多重確定の防止 (`extract_deterministic_prematches`)**:
   [`extract_deterministic_prematches`](file:///mnt/workspace/S.S.T/src/sst/llm/prematch.py#L154-L230) において、複数の異なる正規化タイトルを持つローカルトラックが同一の `matched_v_idx` を指している場合（フォーマット違いではなく別曲の衝突）、それらを決定論的確定から外し、`unmatched_local_tracks` および `unfilled_steam_slots` に残して LLM Phase 2 の判断に委ねる。

### 3.2 `src/sst/llm/organizer.py` の修正
[`LLMOrganizer.align_slots`](file:///mnt/workspace/S.S.T/src/sst/llm/organizer.py#L680) の680行目を修正する：
- **修正前**:
  ```python
  if not unmatched_local_tracks or not unfilled_steam_slots:
  ```
- **修正後**:
  - `not unmatched_local_tracks and not unfilled_steam_slots`（未確定ローカルトラックが0件 **かつ** 空きSteamスロットが0件）のときのみ、「すべてのトラックが決定論的プレマッチで確定」として `confidence = 100` を付与し Phase 2 をバイパスする。
  - もし `not unmatched_local_tracks` だが `unfilled_steam_slots` が残っている場合（例: ローカルファイル数自体がSteamスロット数より少ない欠番アルバム等）は、Phase 2に送るべき未確定ローカルトラックが存在しないため `_run_differential_segments` は呼ばないが、**「全スロット確定による確信度100%への引き上げ」は行わず**（`global_res` の Phase 1 確信度を維持）、そのまま後段の検証へ進める。
  - 逆に `unmatched_local_tracks` が残っていて `unfilled_steam_slots` が空の場合、未確定ローカルトラックがどのSteamスロット（全参照 `full_ref_steam`）に入るべきか、または本当に `unassigned_files` かを判定するため、`unfilled_steam_slots or full_ref_steam` を参照として `_run_differential_segments` を実行する。

### 3.3 `src/sst/processing/duplicate_mappings.py` の修正
1. [`_resolve_multidisc_index_conflicts`](file:///mnt/workspace/S.S.T/src/sst/processing/duplicate_mappings.py#L108-L118) および [`_resolve_disc_title_matches`](file:///mnt/workspace/S.S.T/src/sst/processing/duplicate_mappings.py#L133-L156)、[`_resolve_sequential_track_duplicates`](file:///mnt/workspace/S.S.T/src/sst/processing/duplicate_mappings.py#L171-L180) において：
   - `tid` からローカルタイトルを取り出す際は必ず `raw_local = tid.split("_", 1)[1].split("::", 1)[0]` として `::file_id` を除去する。
   - さらに `track_groups` 内に埋め込みタグのタイトル（`meta.get("title")`）があればそれも候補に加える。
   - Steamタイトルとローカルタイトルの比較には `TrackManager.normalize_title` を使用し、句読点・記号差（`They're Here!` vs `They're Here`、`Cowards Crossing` vs `Coward's Crossing`、`CAST _ CREW` vs `Cast & Crew` 等）を吸収した上で一致および `SequenceMatcher`（閾値 `>= 0.80`）を判定する。
2. `_resolve_disc_title_matches` では、`local_disc`（ローカルが全曲 `disc=1` の場合がある）だけでなく、同一 `v_idx` に衝突しているトラック群のタイトルが **他ディスクの未割当または衝突元のSteamスロット** と一致する場合にも正しい `steam_idx` を復元できるように検索範囲を `store_tracks` 全体に広げる（同一ディスクの一致を最優先し、なければ全ディスクで一意にタイトル一致するSteamスロットへ再配置する）。

---

## 4. 不変条件・禁止事項

- トラック番号と再生時間（尺）の一致のみを根拠に、タイトル不一致またはタイトル空のトラックを `is_deterministic = True` にしてはならない。
- 複数ディスクでタイトルも同じ曲（例: Disc 1 Track 1 `"Main Theme"` と Disc 2 Track 1 `"Main Theme"`）があり、ローカル側のディスク番号から一意に区別できない場合は、勝手に片方へ確定させず非決定論的（LLMまたはローカルディスク構造）に委ねること。

---

## 5. テスト作成指示

`tests/test_differential_alignment.py` および `tests/test_batch_accuracy_improvements.py` に以下の回帰テストを追加すること。

1. **`test_multidisc_prematch_does_not_overwrite_disc1_with_disc2_or_disc3`**:
   - **設定**: Disc 1（Track 1 `"Main Theme"`, Track 2 `"The Calm"`）、Disc 2（Track 1 `"The Pale Reach"`, Track 2 `"Icebreaker"`）、Disc 3（Track 1 `"The Iron Rig Theme"`, Track 2 `"Dark Splash"`）の3枚組Steamトラックリストと、フラットまたはディスク別のローカルトラック6曲、およびトラック番号 `1, 2` を持つ `full_ref_fingerprint` を用意する。
   - **検証**: `resolve_prematch_signals` を実行した際、Disc 1の `"01 Main Theme"` が Disc 3の `v_idx=4` (`"The Iron Rig Theme"`) に割り当てられないこと。各トラックがタイトル整合する自身のディスクの `v_idx` にのみ決定論的マッチすること。
2. **`test_align_slots_does_not_bypass_phase2_when_steam_slots_remain_unfilled`**:
   - **設定**: Steam 4スロットに対し、決定論的プレマッチで2スロットのみ埋まり `unfilled_steam_slots` が2件残っているケース。
   - **検証**: `unmatched_local_tracks` が存在する場合は必ず `_run_differential_segments` が呼ばれること。また、ローカルファイル自体が2曲しかなく `unmatched_local_tracks` が空の場合は、Phase 1の低い確信度が勝手に `100%`（`"すべてのトラックが決定論的プレマッチで確定"`）に書き換えられないこと。
3. **`test_resolve_disc_title_matches_strips_file_id_and_punctuation`**:
   - **設定**: `tid = "1_they re here::abcdef1234567890"`（元ファイル `05 They're Here!.mp3`）と `tid = "1_cowards crossing::1234567890abcdef"` が Disc 2のスロット `v_idx=26` に衝突しており、Disc 1の `v_idx=4` が `"They're Here"`、`v_idx=5` が `"Coward's Crossing"` である合成データ。
   - **検証**: `resolve_duplicate_mappings` 実行後、`::file_id` サフィックスやアポストロフィ・感嘆符の差異に影響されず、それぞれ `v_idx=4` と `v_idx=5` に正しく復元されること。

---

## 6. 完了条件・検証コマンド

```bash
rtk uv run pytest tests/test_differential_alignment.py tests/test_batch_accuracy_improvements.py
rtk uv run pytest
```
すべての既存テストおよび新規追加テストがパスすること。
