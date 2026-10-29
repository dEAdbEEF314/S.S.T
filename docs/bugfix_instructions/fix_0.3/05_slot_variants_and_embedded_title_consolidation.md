# 修正指示書 05: タグなしWAVとタグ付きMP3のバリアント統合強化・カテゴリ接頭辞/同名連番スロット対応および構造的スロット残差確定（Pass 3）

## 1. 背景と問題の概要

全352件バッチ処理の監査において、[`src/sst/llm/prematch.py`](file:///mnt/workspace/S.S.T/src/sst/llm/prematch.py), [`src/sst/processing/slot_variants.py`](file:///mnt/workspace/S.S.T/src/sst/processing/slot_variants.py), および [`src/sst/processing/unassigned.py`](file:///mnt/workspace/S.S.T/src/sst/processing/unassigned.py) における同一スロットのフォーマットバリアント統合および残差確定ロジックの不備により、**9件の Review アルバム** でロスレスWAVが未割当として取り残されたり、スロット番号と再生時間が100%一致している多言語・略称トラックが未確定のまま Review 落ちする事象が確認された。

### 発生している現象（実データ例）
1. **【Steamカテゴリ接頭辞 `ME 01 - ` / `(unused)` 表記および同名連番スロットによるロスレスWAV取り残し】AppID `1167720` (Artifact Adventure Gaiden DX Soundtrack)**:
   - 全43曲、各曲 WAV（埋め込みタグなし）＋ MP3（Steam公式タイトルと同一の埋め込みタイトル付き）の計86ファイル。
   - **問題A（Slots 20, 21, 22 の同名3連続スロット）**:
     - Steam 定義では Slot 20, 21, 22 の3曲がすべて **同一タイトル `"Dungeon - Artificial"`**（それぞれ 116秒, 134秒, 129秒）になっている。
     - ローカルファイルは `20 - Dungeon Artifical 1.wav/.mp3`（116秒、WAVは `Artifical` と1文字タイポ）、`21 - Dungeon Artificial 2.wav/.mp3`（134秒）、`22 - Dungeon Artificial 3.wav/.mp3`（129秒）であり、末尾に連番 `1`, `2`, `3` が付いている。
     - `prematch.py` および `unassigned.py` の `_has_conflicting_numbers_or_qualifiers` が、ローカル側の数値トークン `{"1"}`, `{"2"}`, `{"3"}` と Steam 側の `set()`（数値なし）を「数値競合」とみなして弾いたため、Slot 20, 21, 22 のMP3/WAVが未割当として残った。
   - **問題B（Slots 30, 31, 32, 34, 39, 40, 41 のタグなしWAV取り残しとMP3誤採用）**:
     - 例として Slot 30 の Steam 公式タイトルは `"ME 01 - Quest"`、Slot 34 は `"Battle - Mirai 02 (unused)"`。
     - MP3（`30 - Quest.mp3`, `34 - Battle Mirai 02.mp3`）には埋め込みタイトル `"ME 01 - Quest"`, `"Battle - Mirai 02 (unused)"` があるため決定論的プレマッチでSlot 30, 34に確定した。
     - 一方、同じファイル名ステムを持つタグなし WAV（`30 - Quest.wav`, `34 - Battle Mirai 02.wav`）は、ファイル名に `"ME 01 - "` や `"(unused)"` がないためプレマッチから漏れた。
     - 本来であれば後段の `slot_variants.py` で、既に Slot 30 に割り当てられた `30 - Quest.mp3`（`norm_stem = "quest"`）と未割当の `30 - Quest.wav`（`norm_stem = "quest"`）が統合されるはずだったが、`slot_variants.py:165-184` で `other_steam_matches` を計算する際、`"quest"` が Slot 31 `"ME - Quest 2 (unused)"` や Slot 32 `"ME - Quest 3 (unused)"` にも部分一致したため `no_conflicting_other_slot` が `False` となり、**同一ファイル名ステム（`unaligned_title == assigned_title == "quest"`）であるにもかかわらず `cond2` 側に流れたり、Phase 2 で別スロットに誤配置されたりして、ロスレス WAV 7曲が `unassigned/` に捨てられ MP3 が採用された**！
2. **【本編の大半が確定済みのアルバムにおける、同一スロット番号・同一再生時間の多言語/略称トラックの未確定】**:
   - **AppID `2260070` (Undying Original Soundtrack)**:
     - 全13曲（各 FLAC + MP3）。Slot 1〜10 は英語タイトルで100%決定論的に確定済み。
     - 残り3つの空きスロットは Slot 11（`《送别》中年安玲版`, 117秒）、Slot 12（`《送别》少年安玲版`, 117秒）、Slot 13（`《送别》科迪版`, 112秒）。
     - 未割当として残っているローカルファイルは `11 Farewell By Anling.flac/.mp3`（`disc=1, n=11`, 117.1秒）、`12 Farewell By Young Anling.flac/.mp3`（`disc=1, n=12`, 117.1秒）、`13 Farewell By Cody.flac/.mp3`（`disc=1, n=13`, 112.1秒）のちょうど3組のみ！
   - **AppID `3162910` (Parking Garage Rally Circuit Original Soundtrack)**:
     - 全15曲。11曲が決定論的に確定済み。
     - 残り4つの空きスロットは Slot 10（`Minneapolis`, 174秒）、Slot 12（`Race Complete 1`, 4秒）、Slot 13（`Race Complete 2`, 4秒）、Slot 14（`Race Complete 3`, 5秒）。
     - 未割当のローカルファイルは `10 MPLS.mp3`（`n=10`, 174.1秒、Minneapolisの略称）、`12 Race Complete Poor.mp3`（`n=12`, 4.4秒）、`13 Race Complete Average.mp3`（`n=13`, 4.9秒）、`14 Race Complete Good.mp3`（`n=14`, 5.7秒）のちょうど4曲のみ！
   - **AppID `336870`, `442101`, `466530`, `566260`, `840070`, `959840`**:
     - いずれも全スロットの `(disc, n)` と再生時間がローカルの FLAC+MP3 ペアと1対1で完全に対応している多言語アルバム。

---

## 2. 原因箇所と現行コードの欠陥

### 2.1 `src/sst/llm/prematch.py` (`_titles_match`: 173〜195行目 / `_has_conflicting_numbers_or_qualifiers`: 78〜96行目)
1. **同一スロット・同一尺（`same_slot_and_duration`）時における括弧内修飾語 `(unused)` の先行未除去**:
   - `_titles_match`（183行目）は、先に `_has_conflicting_numbers_or_qualifiers(l_cand, s_main)` を呼び出してから、その後の185行目で括弧 `(...)` を除去している。
   - そのため、Steam タイトル `"Battle - Mirai 02 (unused)"` に含まれる `"unused"`（`_VERSION_QUALIFIERS` に含まれる）が183行目で弾かれ、185行目の括弧除去ロジックに一切到達しない！
2. **Steam 側のカテゴリ接頭辞（`"ME 01 - Quest"` → `"Quest"`）の未分離**:
   - `_candidate_local_titles` はローカル側の `"<Artist/Prefix> - <Title>"` を分割するが、Steam 側の `"ME 01 - Quest"` や `"ME - Quest 2 (unused)"` の `" - "` 以降のコアタイトル（`"quest"`, `"quest 2"`）を抽出していない。
3. **Steam 側で連続する同名スロット（`"Dungeon - Artificial"` ×3）に対するローカル連番サフィックス（`1`, `2`, `3`）の非許容**:
   - Steam 側に数値がなくローカル側に `1`, `2`, `3` がある場合、無条件で `_has_conflicting_numbers_or_qualifiers` が `True`（競合）を返すため、Steam 側で同名タイトルが複数スロットにまたがっていてローカル側が `1, 2, 3` で区別しているケースに対応できない。

### 2.2 `src/sst/processing/slot_variants.py` (`consolidate_slot_variants_and_deduplicate`: 140〜205行目)
- `unaligned_tracks`（例: `30 - Quest.wav`）は Phase 2 前にプレマッチから漏れるため、そもそも `prematch.py` の `extract_deterministic_prematches` 時点で、**同じ `(disc, track_num)`・同じ `norm_stem`（または1文字タイポ以内）・再生時間差 ±2.0秒以内** の別フォーマット兄弟ファイル（例: `30 - Quest.mp3`）が既に特定の `v_idx` にプレマッチされているなら、その場でタグなし WAV も同じ `v_idx` に決定論的プレマッチとして合流させるべきである。
- 目前の `prematch.py` は各ファイルを独立に評価するだけで、同じ `(disc, track_num, norm_stem)` を持つ兄弟フォーマットが埋め込みタイトルによってプレマッチ成功した結果を、タグなしのロスレス兄弟ファイルへ共有していない！
- その結果、タグなし WAV だけが `unmatched_local_tracks` として LLM Phase 2 に送られ、Phase 2 で別スロットに誤配置されたり破棄されたりしていた。

### 2.3 `src/sst/processing/unassigned.py` (`reconcile_deterministic_unassigned_slots`: 82〜224行目)
- Pass 1（完全一致）と Pass 2（部分一致）のみで、タイトル文字列が一切重ならない多言語翻訳タイトル（`《送别》中年安玲版` vs `11 Farewell By Anling`）や都市略称（`Minneapolis` vs `10 MPLS`）に対して、スロット番号 `(disc, n)` と再生時間（`dur_diff <= 2.0s`）の1対1構造整合による Pass 3 が存在しない。

---

## 3. 具体的な修正仕様

### 3.1 `src/sst/llm/prematch.py` の修正
1. **同一 `(disc, track_num)` かつ同一 `norm_stem`（または高類似度）・同一尺のフォーマットバリアントに対するプレマッチ伝播**:
   - `extract_deterministic_prematches`（407〜465行目）において、個別ファイルの `resolve_prematch_signals` ループが完了した後、まだプレマッチされていないローカルトラック `u_track` について：
     - 既に `v_idx_to_candidates[matched_v_idx]` に確定しているトラック `m_track` の中に、以下の条件を **すべて** 満たす兄弟フォーマットが存在するかを検査する：
       1. `u_track` と `m_track` のディスク番号 `d` およびトラック番号 `n` が両方非 None で完全一致していること。
       2. 拡張子（フォーマット）が異なること（例: `.wav` と `.mp3`）。
       3. 再生時間差が `|u_dur - m_dur| <= 2.0` 秒であること。
       4. ファイル名由来の `norm_stem` 同士が完全一致するか、または `SequenceMatcher(None, u_stem, m_stem).ratio() >= 0.88`（例: `"dungeon artifical 1"` vs `"dungeon artificial 1"`）であること。
     - すべて満たす場合、`u_track` も同じ `matched_v_idx` の決定論的プレマッチ候補に追加する！
     - **効果**: これにより、AppID `1167720` のように MP3 にだけ埋め込みタグがあり WAV にタグがないアルバムで、WAV が Phase 2 に迷い込むことなく **プレマッチ段階で100%確実に MP3 と同じスロットに結束**される。
2. **`_titles_match`（173〜195行目）における `same_slot_and_duration` 判定の順序修正と同名スロット連番許容**:
   - `same_slot_and_duration` が `True` の場合：
     - まず `l_cand` と `s_main` の両方から括弧内表記 `(...)` / `[...]`（例: `(unused)`）を除去した `l_no_paren`, `s_no_paren` を作成し、さらに `s_no_paren` に `" - "` が含まれる場合は後半部分（例: `"ME 01 - Quest"` → `"quest"`）も候補 `s_variants` に加える。
     - その `l_no_paren` と `s_var` の組に対して `_has_conflicting_numbers_or_qualifiers(l_no_paren, s_var)` を検査し、競合がなければ完全一致・包含一致・タイポ許容一致（`ratio >= 0.84`）を判定する。
     - さらに、Steam 側 `s_var` に数値トークンがなく、ローカル側 `l_no_paren` が `f"{s_var} {k}"`（末尾に1桁の連番 `k` が付いているだけ、または `Artifical` のような1文字タイポ＋連番 `k`）である場合、もし `full_ref_steam` 内に同じ正規化タイトル `s_main` を持つスロットが複数存在する（例: `"Dungeon - Artificial"` が Slot 20, 21, 22 の3つ存在する）ならば、この末尾連番 `k` を同名曲区別用のサフィックスとして許容し `True` を返す。

### 3.2 `src/sst/processing/slot_variants.py` の修正
1. **同一 `(disc, n)`・異フォーマット・同一 `norm_stem`（または1文字タイポ以内）の最優先統合**:
   - `consolidate_slot_variants_and_deduplicate`（140〜198行目）において、`same_slot_number` かつ `is_different_format` かつ `dur_diff <= 2.0` であり、未割当ファイルの `norm_stem` と割り当て済みバリアントの `norm_stem` が完全一致（または `SequenceMatcher >= 0.88`）する場合は、`other_steam_matches` によるブロックを受けることなく無条件に `cond1_diff_fmt = True` として同一スロットへ統合する。

### 3.3 `src/sst/processing/unassigned.py` (`reconcile_deterministic_unassigned_slots`) の修正
1. **Pass 3（構造的スロット番号＋再生時間一致による残差確定）の追加**:
   - Pass 1（完全一致）および Pass 2（部分一致）の完了後、なお未充足の Steam スロット `missing_slots` と未割当のローカルグループが存在する場合、以下の **厳格な構造整合条件** を満たすときに限り Pass 3 を実行する：
     1. アルバム全体の Steam スロットのうち、既に **70%以上**（または残りの未充足スロット数が4件以下で他がすべて確定済み）のスロットが確定していること。
     2. 未充足の Steam スロット `(s_disc, s_num)` に対して、未割当ローカルファイル群の中に **同じディスク番号 `u_disc == s_disc` かつ同じトラック番号 `u_num == int(s_num)`** を持つ候補グループが存在すること。
     3. その未割当候補グループの全ファイルと当該 Steam スロット `s_track` の再生時間 `s_dur` が両方とも有効（`> 0`）であり、**再生時間差が `|u_dur - s_dur| <= 2.0` 秒以内** で一致していること（または `Race Complete` のようにベースタイトルが一致し尺差が ±1.0秒以内であること）。
     4. 同じ `(s_disc, s_num)` を持つ別の非互換な未割当グループが他に存在しないこと（一意であること）。
     5. ローカルタイトルがアルバム内の別の未充足スロットのタイトルと完全一致していないこと（クロススロット衝突がないこと）。
   - 上記すべてを満たす `(s_disc, s_num)` スロットについては、当該未割当バリアント群（FLAC+MP3等）をそのスロットへ決定論的に統合する。
   - **効果**: これにより、AppID `2260070`（Undying の残り3曲 `11..13`）、AppID `3162910`（PGRC の残り4曲 `10, 12..14`）、および万が一 Phase 2 が失敗した場合の日英バイリンガルアルバム群（`336870`, `442101`, `466530`, `566260`, `840070`, `959840`）が、タイトル言語の壁を超えて構造的・物理的（トラック番号＋秒数完全一致）に100%確定される。

---

## 4. 不変条件・禁止事項

- Pass 3（構造的スロット番号＋再生時間一致）において、Steam 側の再生時間 `s_dur` が不明（`0` または `None`）なスロットに対して、タイトル不一致のままトラック番号だけで未割当ファイルを割り当ててはならない（必ず `s_dur > 0` かつ `|u_dur - s_dur| <= 2.0` 秒の物理的裏付けを必須とする）。
- 全スロットが既に埋まっているアルバムの余剰ボーナストラック（`584382`, `1553350`, `1806720`, `3107200`）は `missing_slots` が空であるため Pass 3 は一切作動せず、仕様通り `unassigned/` 隔離（Review）が維持される。

---

## 5. テスト作成指示

`tests/test_batch_accuracy_improvements.py` に以下の合成回帰テストを追加すること。

1. **`test_prematch_and_variant_consolidation_handles_me_prefix_unused_tag_and_duplicate_dungeon_titles`**:
   - **設定**:
     - Steam スロット:
       - `1_20`: `"Dungeon - Artificial"` (116s)
       - `1_21`: `"Dungeon - Artificial"` (134s)
       - `1_22`: `"Dungeon - Artificial"` (129s)
       - `1_30`: `"ME 01 - Quest"` (8s)
       - `1_34`: `"Battle - Mirai 02 (unused)"` (95s)
     - ローカルファイル（各曲 WAV [タグなし] + MP3 [Steamと同タイトルの埋め込みタグあり]）:
       - `20 - Dungeon Artifical 1.wav` / `.mp3` (116s)
       - `21 - Dungeon Artificial 2.wav` / `.mp3` (134s)
       - `22 - Dungeon Artificial 3.wav` / `.mp3` (129s)
       - `30 - Quest.wav` / `.mp3` (8s)
       - `34 - Battle Mirai 02.wav` / `.mp3` (95s)（AppID `1167720` 型）。
   - **検証**: 全5スロットすべてに WAV と MP3 の両方が統合され、採用ファイルとしてロスレス `.wav` が100%選択され、未割当ファイルが0件になること。
2. **`test_reconcile_deterministic_unassigned_slots_pass3_resolves_bilingual_and_abbreviated_slots_by_number_and_duration`**:
   - **設定**: 全13スロット中 Slot 1〜10 が確定済みで、未充足の Slot 11 (`《送别》中年安玲版`, 117s), Slot 12 (`《送别》少年安玲版`, 117s), Slot 13 (`《送别》科迪版`, 112s) に対し、未割当の `11 Farewell By Anling.flac/.mp3` (117s), `12 Farewell By Young Anling.flac/.mp3` (117s), `13 Farewell By Cody.flac/.mp3` (112s) が存在する場合（AppID `2260070` 型）。
   - **検証**: `reconcile_deterministic_unassigned_slots` が Pass 3 により Slot 11〜13 に FLAC+MP3 を統合し、未充足スロット0件・未割当0件となること。

---

## 6. 完了条件・検証コマンド

```bash
rtk uv run pytest tests/test_batch_accuracy_improvements.py
rtk uv run pytest
```
すべての既存テストおよび新規追加テストがパスすること。

