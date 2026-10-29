# 修正指示書 02: `reject_contradictory_slot_assignments` におけるスロット番号・再生時間一致アンカーの保護と助詞差分の互換判定強化

## 1. 背景と問題の概要

全352件バッチ処理の監査において、LLM Phase 2 の結果から矛盾割当を除去する [`src/sst/llm/assignment_validation.py`](file:///mnt/workspace/S.S.T/src/sst/llm/assignment_validation.py) の `reject_contradictory_slot_assignments` が、別チャンク等から誤って混入した無関係なトラックだけでなく、**そのスロットの本来のトラック番号 `(disc, n)` と再生時間を完全に満たしている正当なトラック群（FLAC + MP3 ペア等）まで巻き添えで全件削除（`retained_tids = set()`）** し、大量の `Missing Slots` と `Unassigned Files` を発生させている事象が **7件の Review アルバム** で確認された。

### 発生している現象（実データ例）
1. **【多言語タイトル（日本語Steam定義 vs 英語ローカルファイル）における正当ペアの全没収】**:
   - 該当AppID: `336870` (One Way Heroics Plus), `442101` (Yomawari: Night Alone), `466530` (htoL#NiQ), `566260` (A Rose in the Twilight), `840070` (The Liar Princess and the Blind Prince), `959840` (The Cruel King and the Great Hero)。
   - これら6件はいずれも Steam スロット定義が日本語タイトル（例: `336870` Slot 1 `"迫る闇のテーマ"`, 68秒）であり、ローカルファイルは英語タイトル付きの FLAC + MP3 ペア（例: `01 The Approaching Darkness.flac` [68秒], `01 The Approaching Darkness.mp3` [68秒]）である。
   - Chunk 1 で Slot 1（`v_idx=0`）に `01 The Approaching Darkness`（FLAC+MP3）が正しく割り当てられた後、Chunk 2 から誤って `09 Subtle Darkness`（Track 9, 108秒）が同じ Slot 1 に混入した。
   - `reject_contradictory_slot_assignments` は Slot 1 に複数の異曲（Track 1 と Track 9）が割り当てられたことを検知するが、英語 `"the approaching darkness"` と日本語 `"迫る闇のテーマ"` は文字列として一致しないため `steam_matches` が空集合 `set()` となり、かつ Phase 2 由来のため `deterministic_matches` も空集合となる。
   - その結果、`retained_tids = set()` となり、**本来の Track 1（`n=1`, 68秒）の FLAC と MP3 まで全て削除**されてしまった。
2. **【日本語タイトルの助詞1文字差（`"は"` vs `"が"`）＋括弧付き補足による全没収】**:
   - **AppID `630380` (Ciel Fledge)**:
     - Steam Slot 10（`v_idx=9, n=10`, 158秒）の公式タイトルは `"かくてゲートが開かれる"`。
     - ローカル Track 10（`10 - かくてゲートは開かれる.mp3`, 埋め込みタイトル `"かくてゲートは開かれる（エンディングBGM）"`, 158.1秒）と、誤って混入した Track 9（`09 - 休息の時.mp3`, 71秒）が `v_idx=9` で衝突した。
     - `"かくてゲートが開かれる"`（9文字）と `"かくてゲートは開かれる"`（9文字）は真ん中の助詞1文字（`が` vs `は`）が異なるため、部分文字列一致（`norm_a in norm_b`）が成立せず、`titles_are_compatible` が `False` を返した。
     - その結果、`steam_matches` が空となり、**正当な Track 10（`10 - かくてゲートは開かれる.mp3`）まで削除**された。

---

## 2. 原因箇所と現行コードの欠陥

### 2.1 `src/sst/llm/assignment_validation.py` (`reject_contradictory_slot_assignments`: 164〜197行目)
```python
        steam_matches = {
            tid
            for tid, cand in candidate_titles.items()
            if title_compatibility(cand, steam_title)
        }
        deterministic_matches = {
            tid for tid in tids if tid in deterministic_prematches
        }
        retained_tids = set()
        if len(steam_matches) == 1:
            retained_tids = steam_matches
        elif len(steam_matches) > 1 and _are_tracks_coherent_variants(
            [local_by_id.get(tid, {}) for tid in steam_matches]
        ):
            retained_tids = steam_matches
        elif len(deterministic_matches) == 1:
            retained_tids = deterministic_matches
```
- `steam_matches`（文字列タイトル一致）と `deterministic_matches`（Phase 2 以前のプレマッチ）の2つしか救済手段がない。
- そのため、多言語アルバム（日英・中英）や軽微な表記揺れアルバムにおいて、異チャンクから1つでも別番号のトラックが誤混入すると、**スロットの `(disc, n)` および再生時間（`dur`）と完璧に一致している本来のトラック（例: `n=1, dur=68s` の FLAC+MP3）を識別して残すロジックが存在しない**。

### 2.2 `src/sst/llm/assignment_validation.py` (`titles_are_compatible`: 22〜43行目)
```python
def titles_are_compatible(title_a: str, title_b: str) -> bool:
    norm_a = TrackManager.normalize_title(title_a)
    norm_b = TrackManager.normalize_title(title_b)
    if not norm_a or not norm_b:
        return False
    if norm_a == norm_b or norm_a in norm_b or norm_b in norm_a:
        return True
```
- 括弧内の補足表記（`（エンディングBGM）` 等）を除去したコアタイトルの比較や、`difflib.SequenceMatcher` による高類似度（助詞1文字差・1文字タイポ等）の判定が含まれていないため、`"かくてゲートが開かれる"` と `"かくてゲートは開かれる（エンディングBGM）"` が非互換と判定される。

---

## 3. 具体的な修正仕様

### 3.1 `src/sst/llm/assignment_validation.py` (`titles_are_compatible`: 22〜43行目) の強化
1. **括弧内補足表記を除去したコアタイトル比較の追加**:
   - `title_a`, `title_b` から丸括弧・角括弧（`(...)`, `（...）`, `[...]`, `【...】`）を除去した文字列も正規化し、コアタイトル同士が完全一致または包含一致（数値・バージョン修飾語の競合がない場合）するかを判定する。
2. **高類似度（1文字助詞差・軽微タイポ）の互換判定**:
   - 正規化後の文字列（または括弧除去後のコアタイトル）の文字数がともに5文字以上であり、末尾または内部の数値トークンが競合しておらず、`difflib.SequenceMatcher(None, core_a, core_b).ratio() >= 0.85` を満たす場合（例: `"かくてゲートが開かれる"` vs `"かくてゲートは開かれる"` は `ratio = 8/9 = 0.889 >= 0.85`）は `True` を返す。

### 3.2 `src/sst/llm/assignment_validation.py` (`reject_contradictory_slot_assignments`: 160〜198行目) の修正
1. **スロット番号 `(disc, n)` ＋ 再生時間整合による正当バリアント群の保持**:
   - `not retained_tids` の場合、`steam_tracks[matched_v_idx]` からスロットの期待ディスク番号 `expected_disc = int(steam_track.get("d", 1) or 1)`、期待トラック番号 `expected_num = _extract_track_num({"n": steam_track.get("n")})`、および期待再生時間 `expected_dur = float(steam_track.get("dur") or steam_track.get("duration_s") or 0)` を取得する。
   - 衝突している `tids` の中から、以下の条件を満たす部分集合 `slot_num_and_dur_matches` を抽出する：
     1. ローカルトラックのディスク番号 `int(track.get("d", 1) or 1)` が `expected_disc` と一致し、かつ `_extract_track_num(track) == expected_num` であること。
     2. `expected_dur > 0` かつローカルトラックの再生時間 `local_dur > 0` の場合、`|local_dur - expected_dur| <= 3.0` 秒であること（`expected_dur <= 0` の場合は番号一致のみで確認）。
   - `slot_num_and_dur_matches` が **1件以上存在し、かつ全 `tids` の真部分集合である**（＝別番号または別尺の誤混入トラックが存在する）場合において：
     - `len(slot_num_and_dur_matches) == 1`、または `_are_tracks_coherent_variants([local_by_id.get(tid, {}) for tid in slot_num_and_dur_matches])` が `True` であれば、**`retained_tids = slot_num_and_dur_matches` として正当なトラック群を保護**し、誤混入した残りの `tids` のみを `rejected_tids` として排除する。

---

## 4. 不変条件・禁止事項

- 同じトラック番号を持つが異なる曲（再生時間が3秒以上乖離している、または互いに別曲で `_are_tracks_coherent_variants` が `False` となる複数候補）が同一スロットで衝突している場合は、安易に片方を残さず従来通り矛盾として排除すること。
- 数値トークンが異なる連番曲（例: `"Stage 1"` と `"Stage 2"`）を `SequenceMatcher >= 0.85` で誤って互換と判定しないよう、両方に数値トークンが含まれ数値集合が異なる場合は必ず `False` とすること。

---

## 5. テスト作成指示

`tests/test_batch_accuracy_improvements.py` に以下の合成回帰テストを追加すること。

1. **`test_reject_contradictory_slot_assignments_retains_bilingual_format_pair_matching_slot_number_and_duration`**:
   - **設定**:
     - Steam Slot 1 (`v_idx=0, d=1, n=1, t="迫る闇のテーマ", dur=68`)。
     - ローカルトラック:
       - `tid="f1_flac"`: `d=1, n=1, title="01 The Approaching Darkness", dur=68, ext=".flac"`
       - `tid="f1_mp3"`: `d=1, n=1, title="01 The Approaching Darkness", dur=68, ext=".mp3"`
       - `tid="f9_mp3"`: `d=1, n=9, title="09 Subtle Darkness", dur=108, ext=".mp3"`（Chunk 2 からの誤混入）
     - `v_idx=0` に `["f1_flac", "f1_mp3", "f9_mp3"]` が割り当てられた状態（AppID `336870` 型）。
   - **検証**: `reject_contradictory_slot_assignments` 実行後、`f9_mp3` のみが排除され、Slot 1（`v_idx=0`）には正当な `["f1_flac", "f1_mp3"]` の両方が保持されること。
2. **`test_titles_are_compatible_handles_japanese_particle_diff_and_parenthetical_note`**:
   - **設定**: Steamタイトル `"かくてゲートが開かれる"` とローカルタイトル `"かくてゲートは開かれる（エンディングBGM）"`（AppID `630380` 型）。
   - **検証**:
     - `titles_are_compatible("かくてゲートは開かれる（エンディングBGM）", "かくてゲートが開かれる")` が `True` を返すこと。
     - 一方、`"Stage 1"` と `"Stage 2"` に対しては `False` を返すこと。

---

## 6. 完了条件・検証コマンド

```bash
rtk uv run pytest tests/test_batch_accuracy_improvements.py
rtk uv run pytest
```
すべての既存テストおよび新規追加テストがパスすること。

