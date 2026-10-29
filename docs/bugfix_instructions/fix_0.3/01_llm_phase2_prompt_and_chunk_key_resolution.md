# 修正指示書 01: LLM Phase 2 プロンプトの複合キー必須化・異フォーマットペア保持チャンク分割・部分リスト `v_idx` 衝突排除

## 1. 背景と問題の概要

全352件バッチ処理の監査において、LLM Phase 2（トラックマッピング）を経由したアルバムのうち **14件（Review 13件・誤Archive 1件）** で、プロンプトの出力キー形式とチャンク分割・スロット解決ロジック（[`src/sst/llm/organizer.py`](file:///mnt/workspace/S.S.T/src/sst/llm/organizer.py), [`src/sst/llm/prompts.py`](file:///mnt/workspace/S.S.T/src/sst/llm/prompts.py), [`src/sst/llm/normalization.py`](file:///mnt/workspace/S.S.T/src/sst/llm/normalization.py)）の不整合により、正当なトラックが別スロットに誤配置されたり全件破棄される事象が確認された。

### 発生している現象（実データ例）
1. **【Chunk 2 の相対番号 `"1"`〜`"5"` 出力による Chunk 1 結果の上書き・矛盾崩壊】**:
   - 該当AppID: `336870` (6曲欠落), `442101` (4曲欠落), `466530` (3曲欠落), `566260` (3曲欠落), `840070` (7曲欠落), `959840` (4曲欠落)。
   - 例として AppID `336870`（全13曲、各曲 FLAC + MP3 の計26ファイル）では、`unmatched_local_tracks`（26ファイル）が `chunk_size=17` で2つのチャンク（Chunk 1: 17ファイル [Track 1〜8のFLAC+MP3およびTrack 9のFLACのみ]、Chunk 2: 9ファイル [Track 9のMP3およびTrack 10〜13のFLAC+MP3]）に分割された。
   - この際、**Track 9 の FLAC と MP3 が別チャンクに引き裂かれた**だけでなく、Chunk 2 において LLM が Track 9〜13 に対して実際のスロット番号 `"9"`〜`"13"` ではなく **チャンク内の1始まり相対連番 `"1"`, `"2"`, `"3"`, `"4"`, `"5"`** を JSON キーとして出力した（かつ `data/llm_cache.json` の旧キャッシュがヒットした）。
   - その結果、Chunk 2 の Track 9〜13 が **Slot 1〜5 に誤合流**し、後段の `reject_contradictory_slot_assignments` で Slot 1〜5 の全トラックが矛盾として没収された。
2. **【部分リスト（`unfilled_steam_slots`）における相対連番キーの全件破棄（`instruction_count=0`）】**:
   - 該当AppID: `2260070` (Undying: 残り3スロット `n=11, 12, 13` に対し LLM がキー `"1"`, `"2"`, `"3"` を出力 → 全破棄), `3162910` (PGRC: 残り4スロット `n=10, 12, 13, 14` に対し LLM がキー `"1"`, `"2"`, `"3"`, `"4"` を出力 → 全破棄), `689920` (N++: 残り3スロット `n=49, 51, 56` に対しキー `"1"`〜`"4"` を出力 → 全破棄)。
3. **【部分リストにおける 1-based トラック番号キー・0-based `v_idx` キーの別スロット誤解決】**:
   - **AppID `630380` (Ciel Fledge)**: `unfilled_steam_slots` は `[Slot 10 (v_idx=9, n=10), Slot 42 (v_idx=41, n=42)]`。LLM はローカル Track 9 に対してキー `"9"`（1-based `n=9` の意図）を出力し、Slot 10 に対してキー `"10"` を出力した。しかし `resolve_slot_key_to_v_idx`（`normalization.py:113-114`）は、まず `track["n"] == 9` を探して見つからないと、次の `track["v_idx"] == 9` で **キー `"9"` を `v_idx=9`（Slot 10！）に解決**してしまい、Slot 10 に Track 9 と Track 10 の両方が入って矛盾没収された。
   - **AppID `1832420` (Happy’s Humble Burger Farm — 誤Archive)**: `unfilled_steam_slots` は `[Slot 12 (v_idx=11, n=12)]`。LLM は重複した2つ目の Track 11 ファイルに対してキー `"11"`（`n=11` の意図）を出力したが、`resolve_slot_key_to_v_idx` が `track["v_idx"] == 11` で **Slot 12（`Time to Leave`）に誤解決**し、Track 11 の重複音源が Slot 12 として Archive された。
   - **AppID `3638290` (Look Outside)**: `unfilled_steam_slots` に `v_idx=23 (n=24)` と `v_idx=24 (n=25)` が両方存在する状態で、LLM は Track 25（`d1n25`）に対して `reason: "d1n25=='1_25' matches ..."` と書きながら **0-based `v_idx` である `"24"`** をキーとして出力した。`resolve_slot_key_to_v_idx` は `track["n"] == 24` を優先したため、Track 25 のファイルを **1つ前の Slot 24（`v_idx=23, n=24`）に誤解決**した（Slot 21 `v_idx=20` でも全く同じ1ズレが発生）。

---

## 2. 原因箇所と現行コードの欠陥

### 2.1 `src/sst/llm/organizer.py` (`_process_track_mapping_segment`: 419〜445行目)
```python
        while offset < len(segment_tracks):
            chunk = segment_tracks[offset : offset + current_chunk_size]
            prompt = build_mapping_prompt(
                steam_Context,
                chunk,
                degraded=degraded_prompt,
            )
```
1. **プロンプト関数の選択ミスと出力キー形式の曖昧さ**:
   - `prompts.py:4-47` に差分アライメント用の `build_differential_mapping_prompt` が定義されているにもかかわらず、`organizer.py:428` は常に `build_mapping_prompt` を呼び出している。
   - さらに `build_mapping_prompt` / `build_track_mapping_prompt` の `MANDATORY OUTPUT FORMAT` 例示が `"slots": {"1": {"files": ["<FILE_ID>"], ...}}` となっており、かつ入力の `STEAM SLOTS` に明示的な `"slot_key": "1_10"` フィールドが存在しないため、ローカルLLMがチャンクの1番目から順に `"1"`, `"2"`, `"3"` と連番キーを振る誤誘導を引き起こしている。
   - また、プロンプト文字列が変わらなかったため、`fix_0.2` 以前のキャッシュ（`data/llm_cache.json`）が24件のAppIDでそのまま `cache_hit=True` として再利用された。
2. **固定スライスによる異フォーマットペア（FLAC+MP3等）のチャンク分断**:
   - `segment_tracks` は物理ファイル単位（1ファイル1エントリ）のリストであるため、`segment_tracks[offset : offset + current_chunk_size]` で単純スライスすると、同一トラック番号・同一曲名の FLAC と MP3 が Chunk 1 の末尾と Chunk 2 の先頭に分断される。

### 2.2 `src/sst/llm/normalization.py` (`resolve_slot_key_to_v_idx`: 57〜125行目 / `normalize_track_mapping_result`: 128〜221行目)
```python
    if is_partial_list:
        for track in steam_tracks:
            try:
                if int(track.get("n", -1)) == value:
                    return int(track["v_idx"])
            except (TypeError, ValueError):
                continue
        for track in steam_tracks:
            try:
                if int(track.get("v_idx", -1)) == value:
                    return int(track["v_idx"])
            except (TypeError, ValueError):
                continue
        return None
```
1. **`is_partial_list` における `track["v_idx"] == value` フォールバックの危険性**:
   - 単一数値キー `"9"` や `"11"` が出力された際、それが割り当て対象ローカルファイルの1始まりトラック番号（`track_num == 9` や `11`）であるにもかかわらず、`unfilled_steam_slots` 内に `n == 9` が存在しないと、たまたま `v_idx == 9`（1始まりでは `n == 10`！）である次のスロットに誤マッチしてしまう（`630380`, `1832420`）。
   - 逆に LLM が 0始まり `v_idx`（例: `"24"` = `n=25`）を意図して出力した際に、`unfilled_steam_slots` に `n=24`（`v_idx=23`）も残っていると、`track["n"] == 24` に吸い寄せられて1つ前のスロットに誤解決される（`3638290`）。
2. **`reason` フィールドおよびローカルファイルメタデータとの整合性未検証**:
   - LLM が `reason` に `"d1n25=='1_25'"` や `"Slot 10"` と明記していても、`resolve_slot_key_to_v_idx` は `slot_key` 文字列しか見ていない。

---

## 3. 具体的な修正仕様

### 3.1 `src/sst/llm/organizer.py` および `src/sst/llm/prompts.py` の修正
1. **Steam スロットペイロードへの明示的 `"slot_key": "<d>_<n>"` 付与とプロンプトの複合キー必須化**:
   - `organizer.py`（および `alignment_inputs.py` で構築される `steam_Context`）において、各 Steam スロット辞書に `"slot_key": f"{s.get('d', 1)}_{s.get('n')}"` を必ず含める。
   - `prompts.py` の `build_track_mapping_prompt` および `build_differential_mapping_prompt` において：
     - スロットのキーには必ず各 `STEAM SLOTS` エントリの **`"slot_key"`（`"<disc>_<track_number>"` 形式、例: `"1_1"`, `"1_10"`, `"2_3"`）をそのまま使用すること**を明記する。
     - 相対的なチャンク内連番（`"1"`, `"2"`, `"3"`）や 0始まりインデックスの使用を禁止する指示を明記する。
     - `MANDATORY OUTPUT FORMAT` の例示キーを `"1"` から **`"<SLOT_KEY>"`（例: `"1_10"`）** に変更する。
     - ※プロンプト文面が更新されることで、`data/llm_cache.json` 内の旧プロンプトに基づくハッシュキーは自動的に無効化（キャッシュミス）され、旧キャッシュによる汚染も同時に解消される。
2. **チャンク分割時の同一トラック（異フォーマットバリアント）分断防止**:
   - `organizer.py:_process_track_mapping_segment`（415〜430行目）において、`segment_tracks` を固定長 `current_chunk_size` で切る際、チャンク境界 `offset + current_chunk_size` の直前と直後のトラックが **同じ `(disc, track_num)` または同じ `norm_stem`** を持つ場合（例: Track 9 の FLAC と MP3）、境界を広げて同一トラックの全フォーマットバリアントが必ず同じチャンクに入るようにスライス範囲を調整する。

### 3.2 `src/sst/llm/normalization.py` の修正
1. **複合キー `"<d>_<n>"` の最優先解決と、`reason` 内の明示的スロット番号との照合**:
   - `normalize_track_mapping_result`（150〜215行目）において、`slot_key` の解決時に `slot_data.get("reason", "")` および割り当てられた `valid_fids` に対応するローカルトラック情報（`local_tracks` の `d`, `n`, `title`, `dur`）を参照できるようにする。
   - `reason` 内に `d(\d+)n(\d+)`、`\b(\d+_\d+)\b`、または `slot\s*#?(\d+)` / `n=(\d+)` が明記されており、それが単一数値 `slot_key`（0-based `v_idx` 等）の解決先 `n` と1つズレている場合（AppID `3638290` の `slot_key="24"`, `reason="d1n25=='1_25'..."` 等）、`reason` およびローカルファイルのトラック番号 `n=25` が一致する `1_25`（`v_idx=24`）へ正しく解決する。
2. **`is_partial_list` における `v_idx` フォールバックの安全ガード**:
   - `is_partial_list` が `True` のとき、単一数値キー `value` に対して `int(track.get("v_idx", -1)) == value` で解決してよいのは、以下の条件を **すべて** 満たす場合のみに制限する：
     1. 割り当てられたローカルファイルのトラック番号 `local_n` が `value` ではないこと（`local_n == value` の場合、LLM は 0-based `v_idx` ではなくローカルの 1-based トラック番号 `value` をそのまま出力しただけであるため、`v_idx == value` [＝Slot `value + 1`] への解決は1曲ズレ誤爆となる。これで `630380` と `1832420` を完全に防ぐ）。
     2. 割り当てられたローカルファイルのトラック番号 `local_n` が解決先スロットの `int(track.get("n", -1))` と一致するか、または解決先スロットと再生時間差が ±3.0秒以内であること。
3. **チャンク内相対連番キー `"1".."K"` に対する決定論的ペアリング救済ガード**:
   - 万が一 LLM が複合キー指示に従わず `"1"`, `"2"`, ..., `"K"` の連番キーを返した場合でも、無条件に `n=1..K`（Slot 1〜K）へ流し込むのではなく：
     - 割り当てられた各 `files` のローカルトラック番号 `(local_d, local_n)` が、`steam_tracks` 内の特定のスロット `(s_d, s_n)` と **番号一致（`local_d == s_d and local_n == s_n`）かつ再生時間差 ±3.0秒以内** を満たす場合は、キー `"1".."K"` の値ではなくその `(s_d, s_n)` スロットへ解決する（これにより `336870`, `442101`, `959840`, `2260070`, `3162910` 等で LLM が `"1".."K"` を返しても、ローカル Track 11 [117s] は確実に Slot 11 [117s] へ解決され、Slot 1 を汚染しない）。
     - 逆に、キー `"1"` に割り当てられたファイルのローカルトラック番号が `local_n == 9` であるのに Slot 1（`s_n == 1`）とはトラック番号もタイトルも一致しない場合は、Slot 1 への誤割当を拒否する。

---

## 4. 不変条件・禁止事項

- LLM に曲名やタグ値を生成させてはならない（スロット割り当てのみ）。
- ローカルトラック番号もタイトルも再生時間も一致しない曖昧な相対キー出力を当て推量でスロットに押し込んではならない（検証条件を満たさないものは未割当のまま残し、後段または Review へ委ねる）。

---

## 5. テスト作成指示

`tests/test_differential_alignment.py` または `tests/test_batch_accuracy_improvements.py` に以下の合成回帰テストを追加すること。

1. **`test_phase2_chunking_never_splits_format_variants`**:
   - **設定**: 13曲×2フォーマット（FLAC + MP3）= 26ファイルの `unmatched_local_tracks` を `chunk_size=17` でチャンク分割する（AppID `336870` 型）。
   - **検証**: Track 9 の FLAC と MP3 が別チャンクに分断されず、同一チャンク内にまとめられること。
2. **`test_normalize_track_mapping_ prevents_partial_list_v_idx_off_by_one_collision`**:
   - **設定**:
     - ケースA（`630380` / `1832420` 型）: `unfilled_steam_slots = [{"v_idx": 11, "d": 1, "n": 12, "t": "Time to Leave", "dur": 120}]`。ローカル Track 11（`n=11, dur=262`）がキー `"11"` で出力された場合、`v_idx=11`（Slot 12）へ誤解決されず破棄されること。
     - ケースB（`3638290` 型）: `unfilled_steam_slots = [{"v_idx": 23, "d": 1, "n": 24, "t": "Slot 24", "dur": 90}, {"v_idx": 24, "d": 1, "n": 25, "t": "Slot 25", "dur": 145}]`。ローカル Track 25（`n=25, dur=145`）がキー `"24"`, `reason="d1n25 matches 1_25"` で出力された場合、Slot 24（`v_idx=23`）ではなく Slot 25（`v_idx=24`）へ正しく解決されること。
3. **`test_normalize_track_mapping_rescues_relative_keys_when_local_track_num_and_duration_match_slot`**:
   - **設定**: `unfilled_steam_slots` が `n=11 (117s), n=12 (117s), n=13 (112s)` の3件で、LLM がキー `"1"`, `"2"`, `"3"` にそれぞれローカル Track 11 (117s), Track 12 (117s), Track 13 (112s) のファイルIDを割り当てた場合（AppID `2260070` 型）。
   - **検証**: 全件破棄（`instruction_count=0`）にならず、`(local_n == slot_n and dur_diff <= 3.0)` の決定論的整合検証により `n=11, 12, 13` の `v_idx` へ正しく解決されること。

---

## 6. 完了条件・検証コマンド

```bash
rtk uv run pytest tests/test_differential_alignment.py tests/test_batch_accuracy_improvements.py
rtk uv run pytest
```
すべての既存テストおよび新規追加テストがパスすること。

