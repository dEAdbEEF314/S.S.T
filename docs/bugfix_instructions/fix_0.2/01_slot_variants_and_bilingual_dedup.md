# 修正指示書 01: 2言語バリアント・同一フォーマット重複・タイポファイル名におけるスロットバリアント統合の修正

## 1. 背景と問題の概要

アライメント確定後のフォーマットバリアント統合（`src/sst/processing/slot_variants.py` の `build_slot_variant_index`）およびスロット内重複解消（`src/sst/processing/duplicate_mappings.py` の `_deduplicate_format_variants_for_slot`）において、**「異なるフォーマット（`assigned_format != unaligned_format`）かつ正規化タイトルが前方一致すること」** を必須条件としているため、以下の3パターンの正当なバリアントファイルがスロットに統合されず `unassigned_files` として取り残され、**Review行き82件中26件の直接原因**となっている。

### 発生している現象（実データ例）
1. **日英2言語フォルダ・2言語ファイル同梱アルバムでの大量 `Unassigned Files`（23件）**:
   - **Capcom Arcade Stadium / 2nd Stadium ミニアルバム 計19件**（`1611180`, `1611200`, `1611210`, `1611230`, `1611240`, `1611250`, `1611260`, `2019160`, `2087680`, `2087700`, `2087710`, `2087720`, `2087730`, `2087740`, `2087750`, `2087760`, `2087780`, `2087800`, `2093740`）:
     Steam 1スロット（日本語曲名）に対し、ローカルに日本語ファイル名3種（`.flac`, `.m4a`, `.mp3`）と英語ファイル名3種（`.flac`, `.m4a`, `.mp3`）の計6ファイルが存在。日本語3ファイルが決定論的プレマッチで1スロットを埋め切ったため、`organizer.py`（747行目 `elif not unfilled_steam_slots:`）によりLLM Phase 2がバイパスされ、英語3ファイルが `build_slot_variant_index` に渡されたが、タイトル不一致かつ同一フォーマット（`.flac == .flac` 等）のため統合されず `[Unassigned Files (3)]` で全19件がReview行き。
   - **AppID `1971340` (ゴシックは魔法乙女"DEATHSMILESリスペクトアレンジ"サウンドトラック)**:
     Steam 18スロットに対し、日本語WAV/MP3（36ファイル）と英語WAV/MP3（36ファイル）の計72ファイルが同梱。日本語36ファイルで全18スロットが確定した後、英語36ファイルが `build_slot_variant_index` で弾かれ `[Unassigned Files (36)]` でReview行き。
   - **AppID `5172510` (むちむちポーク！＆ピンクスゥイーツ Boosted Soundtrack)**:
     Steam 35スロットに対し、日本語WAV/MP3（70ファイル）と英語WAV/MP3（70ファイル）の計140ファイルが同梱。英語70ファイルが弾かれ `[Unassigned Files (70)]`。
   - **AppID `530490` (DoDonPachi Resurrection OST)** / **AppID `630380` (式神の城 - Soundtrack)**:
     日本語タイトルのFLAC一式と英語タイトルのMP3一式が同梱。日本語FLACがプレマッチで確定した後、英語MP3が `build_slot_variant_index` でタイトル不一致により弾かれ、それぞれ `[Unassigned Files (23)]`、`[Unassigned Files (14)]` でReview行き。
2. **同一スロット・異フォーマット間の1文字タイポ・英数字トラック番号表記揺れによる未統合（2件）**:
   - **AppID `2294270` (RHYTHM SPROUT Soundtrack)**:
     全56曲（WAV 56 + MP3 56 = 112ファイル）のうち、Track 12のみMP3が `12. Gingerbread House.mp3`、WAVが `12. Gingebread House.wav`（`r` が1文字抜けたタイポ）。`build_slot_variant_index` が完全一致/前方一致のみしか許容しないため、最高品質の `12. Gingebread House.wav` が未割当（`[Unassigned Files (1)]`）となり、低品質のMP3が採用された上でReview行き。
   - **AppID `3107200` (Anger Foot Soundtrack)**:
     Track 36 `"ate too much pizza"` について、MP3は `36. ate too much pizza.mp3` だがWAVは `12b. ate too much pizza.wav`。正規化後の `"12b ate too much pizza"` と `"ate too much pizza"` が前方一致せずWAVが未割当（`[Unassigned Files (1)]`）。
3. **サブフォルダ重複収録（同一フォーマット重複）およびエンコード末尾無音差による未統合（2件）**:
   - **AppID `916190` (CrossCode Original Soundtrack)**:
     ルート直下の64曲（`.mp3`）とサブフォルダ `./CrossCodeSoundtrack/` 内の64曲（同一 `.mp3`）の計128ファイルが存在。`_deduplicate_format_variants_for_slot` が `best_format != this_format` を必須としているため同一フォーマット（`mp3 == mp3`）を統合できず、後段の `_resolve_disc_title_matches` が暴走して本編スロットを破壊した。
   - **AppID `3449720` (都市伝説解体センター オリジナルサウンドトラック)**:
     全32曲（WAV 32 + MP3 32 = 64ファイル）が100%決定論的プレマッチしたにもかかわらず、Track 32 `32.KIKIKAITAI` のWAVとMP3が統合されず、後段の `_resolve_disc_title_matches` でSlot 20 `KIKIKAITAI (ED edit)` に誤移動されてSlot 32が欠損（`31/32`）した。

---

## 2. 原因箇所と現行コードの欠陥

### 2.1 `src/sst/processing/slot_variants.py` (`build_slot_variant_index`: 80〜145行目)
```python
        for group_key in unaligned_group_keys:
            ...
            is_different_format = (assigned_format != unaligned_format) and bool(assigned_format and unaligned_format)
            duration_matches = abs(assigned_duration - unaligned_duration) <= 3.0 if (assigned_duration > 0 and unaligned_duration > 0) else True
            title_matches = _normalized_titles_match(unaligned_title, assigned_title)
            if is_different_format and duration_matches and title_matches:
                matched_slot_key = slot_key
                break
```
1. `assignment_validation.py`（54〜64行目）には `same_track_coherent`（`normalize_slot_key(disc, inferred_track) == slot_key` かつ `abs(assigned_duration - unaligned_duration) <= 1.5`）の判定が導入されているにもかかわらず、`organizer.py` が `not unfilled_steam_slots` で Phase 2 をバイパスした後の受け皿である `build_slot_variant_index` に同条件が存在しない。
2. そのため、日英2言語タイトル（`unaligned_title != assigned_title`）や日英同一フォーマット（JP WAV + EN WAV、JP FLAC + EN FLAC）、同一サブフォルダ重複（MP3 + MP3）が一切統合されない。
3. `_normalized_titles_match` が `first == second or first.startswith(second) or second.startswith(first)` のみであり、同一 `(disc, track_num)` かつ同一再生時間であっても1文字のタイポ（`gingebread` vs `gingerbread`）や部分一致（`ate too much pizza` in `12b ate too much pizza`）を許容しない。

### 2.2 `src/sst/processing/duplicate_mappings.py` (`_deduplicate_format_variants_for_slot`: 58〜67行目)
```python
        is_different_format = (best_format != this_format) and bool(best_format and this_format)
        duration_difference_ok = abs(best_duration - this_duration) <= 3.0 if (best_duration > 0 and this_duration > 0) else True
        title_matches = (best_norm_title == this_norm_title) or (bool(best_norm_title and this_norm_title) and (best_norm_title in this_norm_title or this_norm_title in best_norm_title))
        slot_duration_matches = abs(best_duration - this_duration) <= 1.5 if (best_duration > 0 and this_duration > 0) else False

        can_merge = is_different_format and duration_difference_ok and (title_matches or slot_duration_matches)
```
1. `is_different_format` が必須であるため、同一フォーマットの重複ファイル（例: `916190` のサブフォルダ内同一MP3や、`1971340` / `5172510` の日本語WAVと英語WAV）が同一スロットに割り当てられた際に統合されない。
2. 異フォーマットで `(disc, track_num)` と正規化タイトルが完全一致している場合でも、WAVとMP3のエンコード末尾無音差が `3.0s` をわずかに超えるケース（または片方のduration取得値が0.0でない端数差のケース）で統合に失敗する。

---

## 3. 具体的な修正仕様

### 3.1 `src/sst/processing/slot_variants.py` の修正
1. **タイトル照合ヘルパー `_normalized_titles_match` の改善**:
   - 完全一致・前方一致に加え、双方が4文字以上で一方のタイトルが他方に単語として含まれる場合（例: `"ate too much pizza" in "12b ate too much pizza"`）、または空白除去後の一致（`first.replace(" ", "") == second.replace(" ", "")`）を一致と判定する。
   - さらに、同じ `(disc, track_num)` を持つバリアント同士（`same_slot_number`）で再生時間差が `<= 3.0s` の場合は、`SequenceMatcher(None, first, second).ratio() >= 0.85`（1〜2文字のタイポ、例: `gingebread house` vs `gingerbread house`）もタイトル整合として許容する。
2. **構造＋再生時間一致（`same_track_coherent`）によるバリアント統合の追加**:
   `build_slot_variant_index` において、未割当グループ `group_key`（`unaligned_disc`, `unaligned_track_num`, `unaligned_duration`, `unaligned_format`, `unaligned_title`）と確定済みスロット `slot_key`（`assigned_disc, assigned_track_num`）を比較する際、以下のいずれかを満たす場合に同一スロットのバリアントとして統合する：
   - **条件1（異フォーマット＋タイトル整合＋尺整合）**:
     `is_different_format and duration_matches (<= 3.0s, またはタイトル完全一致かつ同一トラック番号なら <= 5.0s) and title_matches`
   - **条件2（同一フォーマット完全重複）**:
     `not is_different_format and abs(assigned_duration - unaligned_duration) <= 1.5 and title_matches`（かつ、アルバム内の別スロットに同名タイトルが存在しない、または `(unaligned_disc, unaligned_track_num) == slot_key` であること）
   - **条件3（2言語バリアント等の構造＋尺完全一致 `same_track_coherent`）**:
     - 未割当ファイルの抽出トラック番号から正規化したスロットキー `normalize_slot_key(unaligned_disc, unaligned_track_num)` が `slot_key` と一致する（または `len(steam_meta.store_tracklist or []) == 1` の単一曲ミニアルバムで `slot_key == (1, "1")` である）、**かつ**
     - `assigned_duration > 0 and unaligned_duration > 0 and abs(assigned_duration - unaligned_duration) <= 1.5` である、**かつ**
     - 未割当ファイルの正規化タイトルが、Steamトラックリスト内の **他のどのスロットの正規化タイトルとも一致しない** こと（別スロットの曲が誤って吸収されるのを防ぐガード）。
3. **統合後の優先順位ソート**:
   `slot_variant_index[matched_slot_key]` に追加した後は、`TrackManager.get_audio_format_priority()` の順（同フォーマット内では日本語/Steamタイトル一致側を優先）に安定ソートする。

### 3.2 `src/sst/processing/duplicate_mappings.py` (`_deduplicate_format_variants_for_slot`) の修正
1. `_deduplicate_format_variants_for_slot` において、以下の場合にも `can_merge = True` として最高優先度の `best_tid` に統合する：
   - **異フォーマット**:
     `is_different_format and ((duration_difference_ok and (title_matches or slot_duration_matches)) or (best_norm_title == this_norm_title and same_track_num and abs(best_duration - this_duration) <= 5.0))`
   - **同一フォーマット（サブフォルダ重複・2言語同一フォーマット重複）**:
     `not is_different_format and slot_duration_matches and (title_matches or same_track_num)`
     （※ここで `same_track_num` は、`best_tid` と `tid` の `t_num_val` がともに非空・非 `"0"` で一致し、かつ `disc` も一致すること）。

---

## 4. 不変条件・禁止事項

- 再生時間が `1.5s` 以上異なりタイトルも一致しない未割当ファイル（真正のボーナストラックや効果音ファイル）を、トラック番号だけを手がかりに既存スロットへ統合してはならない。
- 未割当ファイルのタイトルが別のSteamスロットのタイトルと一致している場合（スワップや番号ズレ）に、条件3（構造＋尺一致）で無関係なスロットへ吸収してはならない。

---

## 5. テスト作成指示

`tests/test_batch_accuracy_improvements.py`（または新規 `tests/test_slot_variants_bilingual.py`）に以下の回帰テストを追加すること。

1. **`test_build_slot_variant_index_merges_bilingual_single_slot_minialbum`**:
   - **設定**: Steam 1スロット（`1_1`: `"テーマ・オブ・ソンソン"`、duration 120s）に対し、日本語ファイル3種（`.flac`, `.m4a`, `.mp3`、duration 120.0s）が `1_1` に割当済みで、英語ファイル3種（`Theme of SonSon.flac`, `.m4a`, `.mp3`、duration 120.0s、`t_num_val="1"`）が未割当である合成データ（Capcom Arcade Stadium 型）。
   - **検証**: `build_slot_variant_index` 実行後、全6ファイルがスロット `(1, "1")` のバリアントとして統合され、未割当が残らないこと。
2. **`test_build_slot_variant_index_merges_bilingual_multitrack_wav_and_mp3`**:
   - **設定**: Steam 2スロット（`1_1`: `"風の城"`, `1_2`: `"燃えるハロウィンタウン"`）に対し、日本語WAV/MP3（`01 風の城.wav/.mp3`, `02 燃えるハロウィンタウン.wav/.mp3`）が確定済みで、別フォルダの英語WAV/MP3（`01 Castle of the Wind.wav/.mp3`, `02 Burning Halloween Town.wav/.mp3`、同一尺・同一トラック番号 `1`, `2`）が未割当である合成データ（AppID `1971340` / `5172510` / `530490` 型）。
   - **検証**: 英語WAV/MP3もそれぞれ `(1, "1")`, `(1, "2")` に統合され、未割当ファイルが0件になること。
3. **`test_build_slot_variant_index_merges_minor_filename_typo_variant`**:
   - **設定**: スロット `(1, "12")` に `12. Gingerbread House.mp3`（duration 145.0s）が割当済みで、`12. Gingebread House.wav`（duration 145.0s, `t_num_val="12"`）が未割当である合成データ（AppID `2294270` 型）。
   - **検証**: `12. Gingebread House.wav` がスロット `(1, "12")` に統合され、最高品質フォーマットである `.wav` が先頭（最優先）に配置されること。
4. **`test_deduplicate_format_variants_merges_same_format_subfolder_duplicates`**:
   - **設定**: 同一スロット `v_idx=0` にルートの `01 Title.mp3` とサブフォルダの `01 Title.mp3`（同一タイトル・同一尺 95.0s）が割り当てられている合成データ（AppID `916190` 型）。
   - **検証**: `_deduplicate_format_variants_for_slot` により1つの `tid` に統合され、後段の `_resolve_disc_title_matches` に渡らないこと。

---

## 6. 完了条件・検証コマンド

```bash
rtk uv run pytest tests/test_batch_accuracy_improvements.py
rtk uv run pytest
```
すべての既存テストおよび新規追加テストがパスすること。

